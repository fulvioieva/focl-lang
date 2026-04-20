# Contributing to FOCL

Thank you for your interest in FOCL! This project is in its early stages and contributions of all kinds are welcome — from new primitives to bug reports to documentation improvements.

## How to contribute

### 1. Reporting issues

Open an issue on GitHub if you find a bug, have a suggestion, or want to discuss a design question. Please include:

- The command you ran and the output you got
- Your Python version and OS
- A minimal example to reproduce the problem (if applicable)

### 2. Proposing new primitives

This is the most impactful way to contribute. The FOCL grammar grows by discovering recurring patterns across real codebases.

**Process:**

1. Run `focl init` on a project (your own or any open-source codebase)
2. Review the generated `.focl` file and identify areas where the compression is weak — places where the output is still verbose or awkwardly expressed
3. Propose a new primitive by opening an issue with the label `primitive-proposal` containing:
   - **Name**: the proposed primitive keyword (e.g. `CACHE`, `RETRY`, `SCHEDULE`)
   - **Replaces**: what multi-line pattern it compresses, with a concrete code example
   - **FOCL syntax**: how it would look in `.focl` output
   - **Token delta**: estimated token savings (original vs. compressed)
   - **Generalisability**: does this appear in one framework or across many?

**What makes a good primitive:**
- It replaces a pattern that appears frequently across different projects
- The compressed form is unambiguous — an AI can reconstruct the original without guessing
- It saves at least 5× tokens compared to the original code
- It carries semantic meaning, not just syntactic shorthand

**What does NOT make a good primitive:**
- Abbreviations for the sake of brevity (e.g. shortening `function` to `fn`)
- Patterns specific to a single project or proprietary codebase
- Constructs that lose information — FOCL compression must be lossless

### 3. Adding language/framework support

FOCL currently supports Java, Kotlin, TypeScript, JavaScript, Python, Go, Ruby, PHP, and C#. To add or improve support for a language:

1. Fork the repository and create a branch named `lang/your-language`
2. Add detection logic in the scanner module
3. Add or update prompt templates for the language-specific patterns
4. Run `focl init` on at least 3 real projects in that language and include the compression stats
5. Open a pull request with the results

### 4. Benchmarks and case studies

We need data from real-world projects to validate and improve compression rates. You can help by:

- Running `focl stats` on open-source projects and sharing the results
- Writing a short case study (even just a few paragraphs) describing what worked well and what didn't
- Comparing compression rates across different project sizes, languages, and architectures

All benchmark contributions should go in the `benchmarks/` directory. Please anonymise any proprietary code.

### 5. Documentation

Good documentation is always needed. Areas where help is particularly welcome:

- Tutorials and getting-started guides
- Primitive reference with detailed examples
- Architecture documentation for contributors who want to understand the codebase
- Translations (the project is English-first but Italian and other languages are welcome)

### 6. Code contributions

For bug fixes and features:

1. Fork the repository
2. Create a feature branch (`feature/your-feature` or `fix/your-fix`)
3. Write tests for your changes
4. Make sure all existing tests pass
5. Open a pull request with a clear description of what you changed and why

## Development setup

```bash
git clone https://github.com/focl-lang/focl.git
cd focl
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

Run tests:

```bash
pytest
```

## Code style

- Python code follows PEP 8
- Use type hints for all function signatures
- Keep functions short and focused
- Write docstrings for public functions and classes

## Commit messages

Use clear, descriptive commit messages:

```
feat: add CACHE primitive for memoization patterns
fix: handle empty source files in scanner
docs: add Python microservice case study
bench: add compression stats for django-rest-framework
```

## Pull request guidelines

- One concern per PR — don't mix unrelated changes
- Include tests for new functionality
- Update documentation if your change affects user-facing behaviour
- Reference the related issue number if applicable

## Community

- Be respectful and constructive
- Assume good intent
- Focus on the work, not the person
- Welcome newcomers — everyone started somewhere

## Questions?

If you're unsure about anything, open an issue or start a discussion. There are no stupid questions — especially in a project this early. Your perspective as a fresh pair of eyes is valuable.
