.PHONY: all
all: sphinx

# No -W for doctests because that disallows tests with empty output.
SPHINX_DOCTEST_OPTS=-n -d build/doctress .
SPHINXOPTS=-n -W -d build/doctrees .

.PHONY: sphinx
sphinx:
	sphinx-build -b html $(SPHINXOPTS) build/html

.PHONY: coverage
coverage:
	sphinx-build -b coverage ${SPHINXOPTS} build/coverage
	cat build/coverage/python.txt

.PHONY: latex
latex:
	sphinx-build -b latex $(SPHINXOPTS) build/latex

# Building a pdf requires a latex installation.  For macports, the needed
# packages are texlive-latex-extra and texlive-fonts-recommended.
# The output is in build/latex/tornado.pdf
.PHONY: pdf
pdf: latex
	cd build/latex && pdflatex -interaction=nonstopmode tornado.tex

.PHONY: doctest
doctest:
	sphinx-build -b doctest $(SPHINX_DOCTEST_OPTS) build/doctest

clean:
	rm -rf build
