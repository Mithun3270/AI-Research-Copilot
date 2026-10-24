import os
import json
import shutil
import logging
import base64
from io import BytesIO
from pathlib import Path
from typing import List, Optional, Dict, Any
from contextlib import asynccontextmanager
from xml.sax.saxutils import escape

from fastapi import FastAPI, HTTPException, UploadFile, File, Form, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import AliasChoices, BaseModel, Field
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import Image, Paragraph, SimpleDocTemplate, Spacer

from .research_copilot import ResearchCopilot

logger = logging.getLogger("ResearchCopilotAPI")
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")

# Global singleton copilot instance
copilot: Optional[ResearchCopilot] = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initializes the ResearchCopilot singleton on application startup."""
    global copilot
    logger.info("Initializing ResearchCopilot engine...")
    try:
        copilot = ResearchCopilot()
        logger.info("ResearchCopilot engine ready.")
    except Exception as e:
        logger.error(f"Failed to initialize ResearchCopilot engine: {e}", exc_info=True)
        raise e
    yield
    logger.info("Shutting down ResearchCopilot API.")


app = FastAPI(
    title="AI Research Copilot API",
    description="Production-grade AI Research Suite powered by Local FAISS, SentenceTransformers, and Ollama (qwen2.5:3b).",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS configuration for frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# -------------------------------------------------------------
# Request / Response Schemas
# -------------------------------------------------------------
class SearchRequest(BaseModel):
    query: str = Field(..., min_length=2, description="Semantic search query")
    top_k: int = Field(default=5, ge=1, le=20, description="Number of results to retrieve")
    paper_filter: Optional[List[str]] = Field(default=None, description="Optional list of paper filenames to restrict search to")
    category_filter: Optional[List[str]] = Field(default=None, description="Optional categories to restrict search to")
    score_threshold: float = Field(default=0.0, ge=0.0, le=1.0, description="Minimum cosine similarity score")


class AskRequest(BaseModel):
    question: str = Field(..., min_length=2, description="Research question to ask the Copilot")
    top_k: int = Field(default=6, ge=1, le=15, description="Number of context chunks to retrieve")
    paper_filter: Optional[List[str]] = Field(default=None, description="Optional list of paper names to restrict RAG context")
    category_filter: Optional[List[str]] = Field(default=None, description="Optional categories to restrict RAG context")
    save_report: bool = Field(default=False, description="Whether to persist output report to outputs/")


class AnalyzeRequest(BaseModel):
    paper_id: str = Field(
        ...,
        min_length=1,
        validation_alias=AliasChoices("paper_id", "paper_name"),
        description="ID of the indexed paper to analyze",
    )
    save_report: bool = Field(default=False, description="Whether to persist output report to outputs/")


class ArchitectureRetryRequest(BaseModel):
    paper_id: str = Field(..., min_length=1, description="ID of the indexed paper")
    invalid_mermaid: str = Field(..., min_length=1, description="Mermaid source that failed validation")


class AnalysisPDFRequest(BaseModel):
    paper_id: str = Field(..., min_length=1, description="ID of the indexed paper")
    analysis: Dict[str, str]
    architecture: Dict[str, Any]


class CompareRequest(BaseModel):
    paper_names: List[str] = Field(..., min_items=2, description="List of at least 2 paper filenames to compare")
    save_report: bool = Field(default=False, description="Whether to persist output report to outputs/")


class ResearchGapRequest(BaseModel):
    paper_id: str = Field(..., min_length=1, description="ID of the indexed paper to analyze")
    save_report: bool = Field(default=False, description="Whether to persist output report to outputs/")


class LiteratureReviewRequest(BaseModel):
    paper_names: Optional[List[str]] = Field(default=None, description="Subset of papers to synthesize in literature review (or None for all)")
    save_report: bool = Field(default=False, description="Whether to persist output report to outputs/")


class CitationRequest(BaseModel):
    paper_name: str = Field(..., description="Filename of the paper")
    style: str = Field(default="IEEE", description="Citation style: IEEE, APA, MLA, CHICAGO, or ALL")


class PaperSectorRequest(BaseModel):
    category: str = Field(
        ...,
        min_length=1,
        max_length=150,
        validation_alias=AliasChoices("category", "sector"),
        description="Category to assign to the paper",
    )


def _get_engine() -> ResearchCopilot:
    """Dependency helper to get the active copilot engine."""
    if copilot is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Research Copilot engine is not initialized.",
        )
    return copilot


# -------------------------------------------------------------
# Endpoints
# -------------------------------------------------------------
@app.get("/", tags=["General"])
async def root():
    """Root status endpoint with system overview."""
    engine = _get_engine()
    return {
        "message": "AI Research Copilot API is running.",
        "version": "1.0.0",
        "health": engine.get_health(),
        "docs_url": "/docs",
    }


@app.get("/health", tags=["General"])
async def health():
    """Health check for embedding model, FAISS index, and Ollama connection."""
    engine = _get_engine()
    return engine.get_health()


@app.get("/papers", tags=["Knowledge Base"])
async def get_papers():
    """Returns all currently indexed papers with metadata, chunk counts, and page stats."""
    engine = _get_engine()
    papers = engine.get_indexed_papers()
    return {
        "count": len(papers),
        "papers": papers,
        "sectors": [category["name"] for category in engine.get_categories()],
        "categories": engine.get_categories(),
    }


@app.patch("/papers/{paper_name}/category", tags=["Knowledge Base"])
@app.patch("/papers/{paper_name}/sector", tags=["Knowledge Base"], include_in_schema=False)
async def update_paper_sector(paper_name: str, req: PaperSectorRequest):
    """Manually updates or creates the paper's category."""
    engine = _get_engine()
    try:
        result = engine.update_paper_sector(paper_name, req.category)
        return {"status": "success", "data": result}
    except ValueError as ve:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(ve))


@app.post("/upload", tags=["Knowledge Base"])
async def upload_paper(file: UploadFile = File(...)):
    """
    Uploads a new research PDF, extracts text via PyMuPDF, chunks it,
    computes embeddings with the local model, and appends to the FAISS vector index.
    """
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only PDF files are supported.",
        )

    engine = _get_engine()
    save_path = engine.papers_dir / file.filename

    try:
        # Save file to disk
        with open(save_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

        # Index paper
        result = engine.add_paper(str(save_path), filename=file.filename)
        return {
            "status": "success",
            "message": f"Paper '{file.filename}' successfully processed and indexed.",
            "data": result,
        }
    except Exception as e:
        logger.error(f"Error indexing uploaded paper {file.filename}: {e}", exc_info=True)
        if save_path.exists():
            save_path.unlink()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to process and index PDF: {str(e)}",
        )


@app.delete("/papers/{paper_name}", tags=["Knowledge Base"])
async def delete_paper(paper_name: str, delete_file: bool = True):
    """
    Deletes a paper from the vector index, cleans the metadata DataFrame,
    re-indexes remaining vectors to maintain strict synchronization,
    and optionally deletes the PDF file from disk.
    """
    engine = _get_engine()
    try:
        result = engine.delete_paper(paper_name=paper_name, delete_file=delete_file)
        return {
            "status": "success",
            "message": f"Paper '{paper_name}' successfully removed from vector index.",
            "data": result,
        }
    except ValueError as ve:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(ve))
    except Exception as e:
        logger.error(f"Error deleting paper {paper_name}: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete paper: {str(e)}",
        )


@app.get("/paper-file/{paper_name}", tags=["Knowledge Base"])
async def get_paper_file(paper_name: str):
    """Serves the actual PDF file for in-browser preview."""
    engine = _get_engine()
    file_path = engine.papers_dir / paper_name
    if not file_path.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"PDF file '{paper_name}' does not exist on disk.",
        )
    return FileResponse(
        path=file_path,
        media_type="application/pdf",
        filename=paper_name,
    )


@app.post("/search", tags=["Semantic Search"])
async def search_chunks(req: SearchRequest):
    """Searches FAISS vector database with query embedding using cosine similarity."""
    engine = _get_engine()
    try:
        results = engine.search(
            query=req.query,
            top_k=req.top_k,
            paper_filter=req.paper_filter,
            score_threshold=req.score_threshold,
            category_filter=req.category_filter,
        )
        return {
            "query": req.query,
            "count": len(results),
            "results": results,
        }
    except Exception as e:
        logger.error(f"Search failed: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Search failed: {str(e)}",
        )


@app.post("/ask", tags=["RAG Question Answering"])
async def ask_question(req: AskRequest):
    """
    Performs full Retrieval-Augmented Generation (RAG) query.
    Retrieves semantic context chunks and queries Ollama (qwen2.5:3b)
    with strict academic anti-hallucination prompting and page citation tracking.
    """
    engine = _get_engine()
    try:
        result = engine.ask(
            question=req.question,
            top_k=req.top_k,
            paper_filter=req.paper_filter,
            category_filter=req.category_filter,
        )

        if req.save_report:
            out_file = engine.outputs_dir / f"ask_{abs(hash(req.question)) % 100000}.txt"
            with open(out_file, "w", encoding="utf-8") as f:
                f.write(f"QUESTION: {req.question}\n\nANSWER:\n{result.get('answer', '')}\n\nSOURCES:\n")
                for s in result.get("sources", []):
                    f.write(f"- {s.get('paper')} (Page {s.get('page')}, score {s.get('score')}):\n  {s.get('text_snippet')}\n\n")

        return result
    except RuntimeError as re:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(re))
    except Exception as e:
        logger.error(f"Ask query failed: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error processing question: {str(e)}",
        )


@app.post("/analyze", tags=["Paper Analysis"])
async def analyze_paper_endpoint(req: AnalyzeRequest):
    """
    Deeply analyzes a single paper to extract problem statement, methodology,
    algorithms, datasets, results, limitations, and key contributions.
    """
    engine = _get_engine()
    try:
        result = engine.analyze_paper(paper_name=req.paper_id)

        if req.save_report:
            clean_name = Path(req.paper_id).stem.replace(" ", "_")
            out_file = engine.outputs_dir / f"analysis_{clean_name}.txt"
            with open(out_file, "w", encoding="utf-8") as f:
                f.write(
                    f"ANALYSIS REPORT FOR: {req.paper_id}\n\n"
                    f"{json.dumps(result.get('analysis', {}), ensure_ascii=False, indent=2)}\n"
                )

        return result
    except ValueError as ve:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(ve))
    except RuntimeError as re:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(re))
    except Exception as e:
        logger.error(f"Analysis failed: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Paper analysis failed: {str(e)}",
        )


@app.post("/analysis/architecture", tags=["Paper Analysis"])
async def retry_architecture_diagram(req: ArchitectureRetryRequest):
    engine = _get_engine()
    try:
        return engine.generate_architecture_diagram(
            paper_name=req.paper_id,
            invalid_mermaid=req.invalid_mermaid,
        )
    except ValueError as ve:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(ve))
    except RuntimeError as re:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(re))
    except Exception as e:
        logger.error(f"Architecture generation failed: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Architecture generation failed: {str(e)}",
        )


@app.post("/analysis/pdf", tags=["Paper Analysis"])
async def download_analysis_pdf(req: AnalysisPDFRequest):
    try:
        buffer = BytesIO()
        styles = getSampleStyleSheet()
        title_style = styles["Title"]
        heading_style = styles["Heading2"]
        body_style = styles["BodyText"]
        body_style.leading = 14
        font_paths = [
            Path(os.getenv("WINDIR", "C:/Windows")) / "Fonts" / "arial.ttf",
            Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
        ]
        unicode_font = next((path for path in font_paths if path.exists()), None)
        if unicode_font:
            if "ReportUnicode" not in pdfmetrics.getRegisteredFontNames():
                pdfmetrics.registerFont(TTFont("ReportUnicode", str(unicode_font)))
            for style in (title_style, heading_style, body_style):
                style.fontName = "ReportUnicode"
        story = [
            Paragraph(escape(f"Paper Analysis: {req.paper_id}"), title_style),
            Spacer(1, 0.2 * inch),
        ]
        labels = [
            ("problem_statement", "Problem Statement"),
            ("proposed_method", "Proposed Method"),
            ("system_architecture", "System Architecture"),
            ("mathematical_models", "Mathematical Models"),
            ("dataset", "Dataset"),
            ("metrics", "Metrics"),
            ("results", "Results"),
            ("strengths", "Strengths"),
            ("limitations", "Limitations"),
            ("future_work", "Future Work"),
        ]
        for key, label in labels:
            story.append(Paragraph(escape(label), heading_style))
            text = escape(str(req.analysis.get(key, "Not mentioned in the paper"))).replace("\n", "<br/>")
            story.append(Paragraph(text, body_style))
            story.append(Spacer(1, 0.14 * inch))
        architecture = req.architecture
        story.append(Paragraph("Architecture", heading_style))
        if architecture.get("kind") == "original":
            story.append(Paragraph(
                escape(f"Original figure from the paper (page {architecture['page']})"),
                body_style,
            ))
            image_data = architecture.get("image_data", "")
            if image_data.startswith("data:image/png;base64,"):
                image_bytes = base64.b64decode(image_data.split(",", 1)[1])
                figure = Image(BytesIO(image_bytes))
                figure_width, figure_height = figure.imageWidth, figure.imageHeight
                scale = min(6.5 * inch / figure_width, 4 * inch / figure_height, 1)
                figure.drawWidth = figure_width * scale
                figure.drawHeight = figure_height * scale
                story.append(figure)
        else:
            story.append(Paragraph("AI-generated architecture (based on the paper text)", body_style))
            steps = architecture.get("steps", [])
            for index, step in enumerate(steps, start=1):
                story.append(Paragraph(escape(f"{index}. {step}"), body_style))

        document = SimpleDocTemplate(
            buffer,
            pagesize=letter,
            rightMargin=0.7 * inch,
            leftMargin=0.7 * inch,
            topMargin=0.7 * inch,
            bottomMargin=0.7 * inch,
            title=f"Paper Analysis: {req.paper_id}",
        )
        document.build(story)
        buffer.seek(0)
        filename = f"analysis_{Path(req.paper_id).stem}.pdf"
        return StreamingResponse(
            buffer,
            media_type="application/pdf",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )
    except ValueError as ve:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(ve))
    except RuntimeError as re:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(re))
    except Exception as e:
        logger.error(f"Analysis PDF generation failed: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Analysis PDF generation failed: {str(e)}",
        )


@app.post("/compare", tags=["Multi-Paper Comparison"])
async def compare_papers_endpoint(req: CompareRequest):
    """
    Generates comparative analysis and matrix across at least 2 papers,
    covering problem formulation, methodology, datasets, models, and tradeoffs.
    """
    engine = _get_engine()
    try:
        result = engine.compare_papers(paper_names=req.paper_names)
        comparison = result.get("comparison")
        expected_fields = [
            "research_problem",
            "methodology",
            "dataset",
            "ai_models",
            "metrics",
            "key_results",
            "limitations",
            "trade_offs",
        ]
        if not isinstance(comparison, dict):
            raise RuntimeError(f"Paper {req.paper_names[0]} could not be read")
        response_papers = comparison.get("papers")
        response_pairs = comparison.get("pairs")
        if not isinstance(response_papers, list) or len(response_papers) != len(req.paper_names):
            raise RuntimeError(f"Paper {req.paper_names[0]} could not be read")
        if not isinstance(response_pairs, list) or not response_pairs:
            raise RuntimeError(f"Paper {req.paper_names[0]} could not be read")
        for pair in response_pairs:
            if (
                not isinstance(pair, dict)
                or not isinstance(pair.get("papers"), list)
                or len(pair["papers"]) != 2
            ):
                raise RuntimeError(f"Paper {req.paper_names[0]} could not be read")
            pair_parameters = pair.get("parameters")
            if not isinstance(pair_parameters, list) or [
                parameter.get("key") for parameter in pair_parameters if isinstance(parameter, dict)
            ] != expected_fields:
                raise RuntimeError(f"Paper {req.paper_names[0]} could not be read")
        logger.info(
            "Comparison API response papers=%r response=%s",
            req.paper_names,
            json.dumps(result, ensure_ascii=False),
        )

        if req.save_report:
            out_file = engine.outputs_dir / "comparison_report.txt"
            with open(out_file, "w", encoding="utf-8") as f:
                f.write(
                    f"COMPARISON OF: {', '.join(req.paper_names)}\n\n"
                    f"{json.dumps(result.get('comparison', {}), ensure_ascii=False, indent=2)}\n"
                )

        return result
    except ValueError as ve:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(ve))
    except RuntimeError as re:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(re))
    except Exception as e:
        logger.error(f"Comparison failed: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Paper comparison failed: {str(e)}",
        )


@app.post("/research-gap", tags=["Research Gap Detection"])
async def research_gap_endpoint(req: ResearchGapRequest):
    engine = _get_engine()
    try:
        result = engine.detect_research_gaps(paper_id=req.paper_id)

        if req.save_report:
            clean_name = Path(req.paper_id).stem.replace(" ", "_")
            out_file = engine.outputs_dir / f"research_gaps_{clean_name}.json"
            with open(out_file, "w", encoding="utf-8") as f:
                json.dump(result, f, ensure_ascii=False, indent=2)

        return result
    except ValueError as ve:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(ve))
    except RuntimeError as re:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(re))
    except Exception as e:
        logger.error(f"Research gap detection failed: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Research gap detection failed: {str(e)}",
        )


@app.post("/literature-review", tags=["Literature Review"])
async def literature_review_endpoint(req: LiteratureReviewRequest):
    """
    Synthesizes selected papers into a formal Chapter 2: Literature Review
    structured into sections 2.1 to 2.8.
    """
    engine = _get_engine()
    try:
        result = engine.generate_literature_review(paper_names=req.paper_names)

        if req.save_report:
            out_file = engine.outputs_dir / "literature_review_chapter_2.txt"
            with open(out_file, "w", encoding="utf-8") as f:
                f.write(f"CHAPTER 2: LITERATURE REVIEW\nPapers: {', '.join(result.get('papers', []))}\n\n{result.get('literature_review', '')}\n")

        return result
    except ValueError as ve:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(ve))
    except RuntimeError as re:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(re))
    except Exception as e:
        logger.error(f"Literature review generation failed: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Literature review generation failed: {str(e)}",
        )


@app.post("/citation", tags=["Citation Generator"])
async def citation_endpoint(req: CitationRequest):
    """
    Extracts bibliographic data from page 1 and generates formatted citations
    in IEEE, APA, MLA, or Chicago style.
    """
    engine = _get_engine()
    try:
        if req.style.upper() == "ALL":
            # Generate all major styles
            styles = ["IEEE", "APA", "MLA", "CHICAGO"]
            citations = {}
            for s in styles:
                c = engine.generate_citation(paper_name=req.paper_name, style=s)
                citations[s] = c.get("citation", "")
            return {
                "paper": req.paper_name,
                "style": "ALL",
                "citations": citations,
            }
        else:
            result = engine.generate_citation(paper_name=req.paper_name, style=req.style)
            return result
    except ValueError as ve:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(ve))
    except RuntimeError as re:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(re))
    except Exception as e:
        logger.error(f"Citation generation failed: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Citation generation failed: {str(e)}",
        )


@app.get("/outputs", tags=["Output Reports"])
async def list_outputs():
    """Lists all generated report files in the outputs directory."""
    engine = _get_engine()
    files = []
    if engine.outputs_dir.exists():
        for f in engine.outputs_dir.glob("*.txt"):
            files.append({
                "filename": f.name,
                "size_bytes": f.stat().st_size,
                "created_at": f.stat().st_mtime,
            })
    return {"count": len(files), "reports": sorted(files, key=lambda x: x["created_at"], reverse=True)}


@app.get("/outputs/{filename}", tags=["Output Reports"])
async def get_output_report(filename: str):
    """Downloads or displays a generated text report."""
    engine = _get_engine()
    file_path = engine.outputs_dir / filename
    if not file_path.exists():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Report file not found.")
    return FileResponse(path=file_path, media_type="text/plain", filename=filename)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("backend.app:app", host="127.0.0.1", port=8000, reload=True)
