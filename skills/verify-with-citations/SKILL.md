---
name: verify-with-citations
description: Citation format for verification work. Use whenever the user asks to verify, fact-check, confirm, cross-check, or find authoritative backing for a claim.
---

# Verify with citations

When verifying a claim, a paraphrase is not evidence. The user needs to see what the source actually said, who said it, and where to look it up. Quote first, then interpret.

## Citation block

Every cited source renders as a blockquote: the verbatim text, a blank quote line, then the attribution.

```markdown
> "<verbatim text from the source, with the **decisive clause in bold**>"
>
> —— <Author or Organization>, *[<Title>](<URL>) <§Section or other locator>*
```

Rules for the block:

- **Quote verbatim.** Preserve the source's own wording, casing, and notation — including when the source is in a different language from your answer. Never translate inside the quote marks; put any translation outside the block.
- **Bold the decisive span.** The clause that actually settles the question, not the whole quote. If nothing stands out, the quote is probably too long.
- **Elide with `…`**, and never across a point that changes the meaning.
- **Attribute to author or organization.** Personal names when the source is authored (`<First Author> et al.`); the issuing body when it is institutional (`<Vendor or Standards Body>`). Add affiliation when it carries the weight — `<First Author> et al., <Lab or Institution>`.
- **Link the title, append the section path.** Title inside `[...]()`, the locator after the closing paren, all inside one `*...*` italic span. Section paths (`§4 Understanding Performance`, `Ch. 3`, `Table 4`, `p. 7`) only need to get a reader close — approximate is fine, invented is not.

## Source list

With **more than 3 sources**, add a table after the prose. Keep the inline blocks for the sources you actually reasoned from; the table is for scanning and filtering, not a replacement.

```markdown
| Source | Author / Org | Key passage |
|---|---|---|
| *[<Title>](<URL>) <§Section>* | <Author or Organization> | <short quoted fragment, **decisive span in bold**> |
| *[<Title>](<URL>) <§Section>* | <Author> et al., <Institution> | <short quoted fragment, **decisive span in bold**> |
```

When sources disagree or vary in weight, group the table by stance or authority rather than flattening them into one list. A source that turned out not to say what you hoped is still worth listing — it saves the user from re-checking it.

## Honesty constraints

These are what make the format worth anything:

- **Never invent a quote, URL, author, or section number.** A fabricated citation is worse than no citation, because it reads as verified. If you cannot retrieve the text, say so and cite nothing.
- **Mark what you could not confirm**, in place: *(affiliation not stated on the page)*, *(abstract only, full text not retrieved)*, *(quoted via a secondary source, primary not checked)*.
- **Separate the quote from your reading of it.** If a source only supports the claim partially or by inference, say which part is inference.
- **Report findings that contradict your own earlier statement**, and correct it plainly.
- **Date-stamp network sources** when the content can change — "retrieved 2026-10-10" — in the prose or the document's own source section.

## Workflow

1. **Identify the claims** actually in dispute. Verify those; do not pad with citations for things nobody questions.
2. **Fetch primary sources in parallel.** Prefer the original over a summary of it — the paper over a blog about the paper, vendor documentation over a forum rephrasing. When a landing page gives only an abstract, go after the full text (`ar5iv.labs.arxiv.org/html/<id>`, `arxiv.org/html/<id>`) before settling for it.
3. **Re-check numbers yourself** when the claim is computational. A one-off script that recomputes a table beats repeating the table.
4. **Write the answer**: verdict first, then the citation blocks that support it, then the table if over 3 sources.
5. **State the limits** — what is still unverified, and what would settle it.
