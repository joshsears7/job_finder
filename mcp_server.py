"""
mcp_server.py
-------------
Model Context Protocol server for CareerIQ.
Exposes resume scoring, job matching, cover letter generation, and company
research as MCP tools — compatible with Claude Desktop, Cursor, and any
MCP-enabled client.

Run: python mcp_server.py
Requires: pip install mcp (anthropic's MCP SDK)
"""

import sys
import json
import logging
from typing import Any

logging.basicConfig(level=logging.INFO, stream=sys.stderr)
_log = logging.getLogger("careeriq-mcp")


def _run_server():
    try:
        from mcp.server import Server
        from mcp.server.stdio import stdio_server
        from mcp import types
    except ImportError:
        print(
            "MCP SDK not installed. Run: pip install mcp",
            file=sys.stderr,
        )
        sys.exit(1)

    server = Server("careeriq")

    # ── Tool definitions ──────────────────────────────────────────

    @server.list_tools()
    async def list_tools() -> list[types.Tool]:
        return [
            types.Tool(
                name="score_resume_vs_job",
                description=(
                    "Score a resume against a job description using semantic similarity "
                    "and keyword analysis. Returns a 0-100 fit score plus matched and "
                    "missing skills."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "resume_text":     {"type": "string", "description": "Full resume text"},
                        "job_description": {"type": "string", "description": "Full job description text"},
                        "job_title":       {"type": "string", "description": "Job title (optional, improves accuracy)"},
                    },
                    "required": ["resume_text", "job_description"],
                },
            ),
            types.Tool(
                name="generate_cover_letter",
                description=(
                    "Generate a personalized cover letter using Claude Sonnet. "
                    "Tailored to the specific job and candidate's resume."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "resume_text":     {"type": "string", "description": "Full resume text"},
                        "job_title":       {"type": "string", "description": "Job title"},
                        "company":         {"type": "string", "description": "Company name"},
                        "job_description": {"type": "string", "description": "Job description (optional but recommended)"},
                        "candidate_name":  {"type": "string", "description": "Candidate's name"},
                    },
                    "required": ["resume_text", "job_title", "company"],
                },
            ),
            types.Tool(
                name="ats_scan",
                description=(
                    "Run a full ATS scan: keyword match, semantic score, missing skills, "
                    "cliché detection, and formatting tips."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "resume_text":     {"type": "string", "description": "Full resume text"},
                        "job_description": {"type": "string", "description": "Job description to scan against"},
                    },
                    "required": ["resume_text", "job_description"],
                },
            ),
            types.Tool(
                name="research_company",
                description=(
                    "Agentic company intelligence: fetches news, HackerNews mentions, "
                    "funding signals, tech stack, and hiring velocity, then synthesizes "
                    "a dossier with talking points, culture read, and likely interview questions."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "company":         {"type": "string", "description": "Company name"},
                        "role":            {"type": "string", "description": "Role you're applying for"},
                        "company_website": {"type": "string", "description": "Company website URL (optional, improves tech stack detection)"},
                        "resume_text":     {"type": "string", "description": "Your resume text (optional, improves tailoring)"},
                    },
                    "required": ["company"],
                },
            ),
            types.Tool(
                name="get_skill_gaps",
                description=(
                    "Compare a resume against a job description and return matched skills "
                    "and missing skills with AI explanations for how to address each gap."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "resume_text":     {"type": "string", "description": "Full resume text"},
                        "job_description": {"type": "string", "description": "Job description to compare against"},
                    },
                    "required": ["resume_text", "job_description"],
                },
            ),
            types.Tool(
                name="generate_linkedin_about",
                description=(
                    "Generate a personalized LinkedIn About section using Claude Sonnet. "
                    "Hook → 3 bullet points → proof → CTA. 180-220 words."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "resume_text":  {"type": "string", "description": "Full resume text"},
                        "target_role":  {"type": "string", "description": "Target role (optional)"},
                        "name":         {"type": "string", "description": "Candidate name"},
                    },
                    "required": ["resume_text"],
                },
            ),
            types.Tool(
                name="score_output_quality",
                description=(
                    "Evaluate a generated AI output (cover letter, LinkedIn about, interview answer) "
                    "for quality: relevance, grounding in resume, specificity, tone, and keyword coverage."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "generated_text":  {"type": "string", "description": "The AI-generated text to evaluate"},
                        "output_type":     {
                            "type": "string",
                            "enum": ["cover_letter", "linkedin_about", "interview_answer", "cold_dm", "other"],
                            "description": "Type of output being evaluated",
                        },
                        "resume_text":     {"type": "string", "description": "Source resume (for grounding check)"},
                        "job_description": {"type": "string", "description": "Job description (for relevance/keyword check)"},
                    },
                    "required": ["generated_text", "output_type"],
                },
            ),
        ]

    # ── Tool handlers ─────────────────────────────────────────────

    @server.call_tool()
    async def call_tool(name: str, arguments: dict[str, Any]) -> list[types.TextContent]:
        try:
            result = await _dispatch(name, arguments)
            return [types.TextContent(type="text", text=json.dumps(result, indent=2))]
        except Exception as e:
            _log.exception("Tool %s failed", name)
            return [types.TextContent(type="text", text=json.dumps({"error": str(e)}))]

    async def _dispatch(name: str, args: dict) -> Any:
        if name == "score_resume_vs_job":
            from scorer import score_job, get_skill_gaps
            score   = score_job(args["resume_text"], args["job_description"], args.get("job_title", ""))
            matched, missing = get_skill_gaps(args["resume_text"], args["job_description"])
            return {"score": score, "matched_skills": matched[:20], "missing_skills": missing[:10]}

        elif name == "generate_cover_letter":
            from claude_ai import generate_cover_letter_claude
            profile = {
                "raw_text": args["resume_text"],
                "name":     args.get("candidate_name", ""),
            }
            job = {
                "title":       args["job_title"],
                "company":     args["company"],
                "description": args.get("job_description", ""),
            }
            text = generate_cover_letter_claude(profile, job)
            return {"cover_letter": text or "Generation failed — check ANTHROPIC_API_KEY"}

        elif name == "ats_scan":
            from ai_tools import ats_scan
            return ats_scan(args["resume_text"], args["job_description"])

        elif name == "research_company":
            from company_research import research_company
            return research_company(
                company=args["company"],
                role=args.get("role", ""),
                company_website=args.get("company_website", ""),
                resume_text=args.get("resume_text", ""),
            )

        elif name == "get_skill_gaps":
            from scorer import get_skill_gaps
            from claude_ai import explain_skill_gaps_claude
            matched, missing = get_skill_gaps(args["resume_text"], args["job_description"])
            explanations = explain_skill_gaps_claude(missing, args["resume_text"], args["job_description"]) or []
            return {
                "matched_skills": matched[:20],
                "missing_skills": missing[:10],
                "gap_explanations": explanations,
            }

        elif name == "generate_linkedin_about":
            from claude_ai import generate_about_claude
            profile = {
                "raw_text": args["resume_text"],
                "name":     args.get("name", ""),
            }
            text = generate_about_claude(profile, args.get("target_role", ""))
            return {"about_section": text or "Generation failed — check ANTHROPIC_API_KEY"}

        elif name == "score_output_quality":
            from eval_engine import evaluate
            return evaluate(
                generated=args["generated_text"],
                output_type=args["output_type"],
                resume_text=args.get("resume_text", ""),
                job_description=args.get("job_description", ""),
                persist=False,
            )

        else:
            raise ValueError(f"Unknown tool: {name}")

    # ── Run ───────────────────────────────────────────────────────
    import asyncio

    async def _main():
        async with stdio_server() as (read_stream, write_stream):
            await server.run(
                read_stream,
                write_stream,
                server.create_initialization_options(),
            )

    asyncio.run(_main())


if __name__ == "__main__":
    _run_server()
