# Blockchain Economics and Digital Assets

Queen Mary, University of London · 2025/2026
Module lead: Dr Daniele Bianchi

This repository holds the LaTeX sources, compiled PDFs, and RAG chunk
file for ECOM215.

## Week-by-week materials

| Week | Lecture slides | Notes | Tutorial (TA copy) |
|-----:|:---------------|:------|:-------------------|
| 0    | [Course Introduction](Lectures/Week%200%20Slides.pdf) | — | — |
| 1    | [Foundations of Blockchain Technology](Lectures/Week%201%20Slides.pdf) | [Notes](Notes/Week%201%20Notes.pdf) | — |
| 2    | [Blockchain Economics](Lectures/Week%202%20Slides.pdf) | [Notes](Notes/Week%202%20Notes.pdf) | [Tutorial](Tutorials/Week%202%20Tutorial%20TA%20Copy.pdf) |
| 3    | [Smart Contracts & DApps](Lectures/Week%203%20Slides.pdf) | [Notes](Notes/Week%203%20Notes.pdf) | [Tutorial](Tutorials/Week%203%20Tutorial%20TA%20Copy.pdf) |
| 4    | [Decentralised Finance (DeFi)](Lectures/Week%204%20Slides.pdf) | [Notes](Notes/Week%204%20Notes.pdf) | [Tutorial](Tutorials/Week%204%20Tutorial%20TA%20Copy.pdf) |
| 5    | [Stablecoins & CBDCs](Lectures/Week%205%20Slides.pdf) | [Notes](Notes/Week%205%20Notes.pdf) | [Tutorial](Tutorials/Week%205%20Tutorial%20TA%20Copy.pdf) |
| 6    | [Digital Ownership & Tokenization](Lectures/Week%206%20Slides.pdf) | [Notes](Notes/Week%206%20Notes.pdf) | [Tutorial](Tutorials/Week%206%20Tutorial%20TA%20Copy.pdf) |
| 7    | [Cryptocurrencies as an Asset Class (I)](Lectures/Week%207%20Slides.pdf) | [Notes](Notes/Week%207%20Notes.pdf) | [Tutorial](Tutorials/Week%207%20Tutorial%20TA%20Copy.pdf) |
| 8    | [Cryptocurrencies as an Asset Class (II)](Lectures/Week%208%20Slides.pdf) | [Notes](Notes/Week%208%20Notes.pdf) | [Tutorial](Tutorials/Week%208%20Tutorial%20TA%20Copy.pdf) |
| 9    | [Blockchain in Traditional Finance](Lectures/Week%209%20Slides.pdf) | [Notes](Notes/Week%209%20Notes.pdf) | [Tutorial](Tutorials/Week%209%20Tutorial%20TA%20Copy.pdf) |

Rebuild the PDFs from source with:

```sh
cd Lectures  && latexmk -pdf *.tex
cd ../Notes  && latexmk -pdf *.tex
cd ../Tutorials && latexmk -pdf *.tex
```

## Chat widget content

The chat widget is backed by **`course-chunks.json`**, a retrieval index
over the course material. Chunks are split on `\section` / `\subsection`
boundaries in the LaTeX sources, and each chunk carries both the cleaned
LaTeX text and the corresponding text extracted from the compiled PDF.

Rebuild the chunk file after editing any source:

```sh
python3 scripts/build_chunks.py
```

This writes `course-chunks.json` in the repo root. Requirements: Python
3.9+ and `pdftotext` on `$PATH` (installed with Poppler or MacTeX).

## Layout

```
ECOM215/
├── README.md                 # this file
├── course-chunks.json        # generated RAG index
├── scripts/
│   └── build_chunks.py       # chunker: .tex + pdftotext → chunks
├── Lectures/                 # Week 0–9 Beamer slides + Figures/
├── Notes/                    # Week 1–9 article-class notes
└── Tutorials/                # Week 2–9 TA-copy tutorial handouts
```
