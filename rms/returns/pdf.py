from fpdf import FPDF

class ReturnFormPDF(FPDF):
    def header(self):
        self.set_font("Arial","B",15)
        self.cell(0,10, f"Return Form #{self.r.id}", ln=True, align="C")

    def footer(self):
        self.set_y(-15)
        self.set_font("Arial","I",8)
        self.cell(0,10, f"Page {self.page_no()}", align="C")

    def body(self):
        r = self.r
        # … same as earlier code …
        # build table of items …
