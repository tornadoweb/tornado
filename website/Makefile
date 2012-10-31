SPHINXOPTS=-W -d sphinx/build/doctrees sphinx

.PHONY: sphinx
sphinx:
	sphinx-build -b html $(SPHINXOPTS) sphinx/build/html

.PHONY: coverage
coverage:
	sphinx-build -b coverage ${SPHINXOPTS} sphinx/build/coverage
	cat sphinx/build/coverage/python.txt

.PHONY: latex
latex:
	sphinx-build -b latex $(SPHINXOPTS) sphinx/build/latex

# Building a pdf requires a latex installation.  For macports, the needed
# packages are texlive-latex-extra and texlive-fonts-recommended.
# The output is in sphinx/build/latex/tornado.pdf
.PHONY: pdf
pdf: latex
	cd sphinx/build/latex && pdflatex -interaction=nonstopmode tornado.tex

clean:
	rm -rf sphinx/build
