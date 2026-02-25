# deep_research

Standard Operating Procedure for multi-turn, in-depth research and analysis of complex technical topics.

## Trigger Patterns
- "Research / investigate / analyze [topic]"
- "How does [system/module] work?"
- "What is the architecture of [component]?"
- Any task requiring multi-step information gathering and synthesis

## Expert Guide (心法)

### Multi-Turn Research Protocol
Research is iterative. Never try to answer everything in one pass.

1. **Plan** (Iteration 1):
   - Start with `## Research Plan`.
   - Identify key aspects to investigate.
   - Provide initial findings from available context.
   - End with `## Next Steps` for the next iteration.

2. **Update** (Iterations 2-N):
   - Start with `## Research Update N`.
   - Build upon previous findings—do NOT repeat.
   - Deep-dive into one specific gap per iteration.
   - Use file reads, web searches, and codebase exploration to gather evidence.

3. **Conclude** (Final Iteration):
   - Start with `## Final Conclusion`.
   - Synthesize ALL findings into a comprehensive, referenced answer.
   - Include specific code references and file paths.
   - Use Mermaid diagrams for architecture/data flow topics.

### Critical Rules
- **Focus Exclusively** on the stated topic. Do not drift.
- **Cite Sources**: Always reference specific files and line ranges.
- **Visualization**: Include Mermaid diagrams for architectural topics.
- **No Padding**: Never respond with just "Continue the research"—always provide substance.

## Required Tools
- `read_file`, `list_files`, `explore_codebase`, `grep_files`
- `crawl_url`, `search_web`
- `manage_memory`

## Verification Contract
The final conclusion MUST directly address the original research question with evidence-backed findings.
