"""
Cover letter template generator (no API key required).

Returns a pre-filled editable template. The user writes the actual
cover letter in the review queue UI before approving.
"""


def generate_cover_letter(
    title: str,
    organization: str,
    description: str,
    job_type: str,
    **kwargs,
) -> str:
    """
    Return a blank cover letter template for the user to fill in the UI.
    """
    if job_type in ("ml_engineer",):
        greeting = "Dear Hiring Committee,"
        closing_note = ""
    else:
        greeting = "Dear Professor / Hiring Committee,"
        closing_note = (
            "\nA recommendation letter is available upon request."
            if job_type in ("phd", "postdoc")
            else ""
        )

    return (
        f"{greeting}\n\n"
        f"I am writing to apply for the {title} position at {organization}.\n\n"
        f"[Introduce yourself and your background — 2-3 sentences]\n\n"
        f"[Explain why this specific role/lab interests you — reference their research]\n\n"
        f"[Describe your most relevant experience and how it fits this position]\n"
        f"{closing_note}\n\n"
        f"I would welcome the opportunity to discuss how my background aligns with your needs.\n\n"
        f"Sincerely,\n"
        f"Hevra Petekkaya\n"
        f"hevrapetekkaya01@gmail.com | +49 17632086462\n"
        f"https://github.com/hevra01"
    )
