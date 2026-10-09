# Printable save-the-date cards

`save-the-date-en.pdf`, `-fr.pdf`, `-ro.pdf` — A5, one card per language, the
same design as the website. The church, the château and the address are real
links, clickable in any PDF reader.

Each `.html` next to them is the source the PDF was made from. To regenerate
after editing one:

* **In a browser** — open the file, print, choose *Save as PDF*, paper size A5,
  margins *None*, and tick *Background graphics* (without it you lose the
  château and the gold).
* **Headless** — `chromium --headless --print-to-pdf=save-the-date-en.pdf
  --no-pdf-header-footer save-the-date-en.html` (Chromium keeps the links;
  Ghostscript and most "optimisers" strip them, so do not post-process).

`chateau-print.jpg` is the backdrop, cropped to the slice an A5 page shows and
sized for print. `docs/chateau.jpeg` is much larger and would quadruple the
file size for no visible gain.
