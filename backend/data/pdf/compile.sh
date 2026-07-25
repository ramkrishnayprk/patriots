#!/bin/sh
set -eu

mkdir -p /docs/build /docs/pdfs /docs/text

for source in /docs/latex/*.tex; do
    filename="${source##*/}"
    stem="${filename%.tex}"

    pdflatex \
        -interaction=nonstopmode \
        -halt-on-error \
        -output-directory=/docs/build \
        "$source"

    cp "/docs/build/${stem}.pdf" "/docs/pdfs/${stem}.pdf"
    pdftotext -layout "/docs/pdfs/${stem}.pdf" "/docs/text/${stem}.txt"
done
