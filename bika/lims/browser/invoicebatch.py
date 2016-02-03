from cStringIO import StringIO

from Products.Five.browser.pagetemplatefile import ViewPageTemplateFile
from Products.CMFCore.utils import getToolByName
from plone.resource.utils import queryResourceDirectory
from zope.i18n.locales import locales

from bika.lims.config import INVOICE_BATCH_TYPES
from bika.lims import bikaMessageFactory as _, t
from bika.lims import logger
from bika.lims.browser import BrowserView
from bika.lims.vocabularies import getStickerTemplates
from bika.lims.browser import BrowserView
from bika.lims.utils import createPdf
from bika.lims.browser.invoice import InvoiceView

from bika.lims.browser.bika_listing import BikaListingView
from bika.lims import bikaMessageFactory as _
from bika.lims.utils import currency_format

import csv
import os
import traceback


class InvoiceBatchInvoicesView(BikaListingView):
    def __init__(self, context, request):
        super(InvoiceBatchInvoicesView, self).__init__(context, request)
        self.contentFilter = {}
        self.title = context.Title()
        types = context.getTypesToInvoice()
        self.description = INVOICE_BATCH_TYPES.getValue(types)
        self.show_sort_column = False
        self.show_select_row = False
        self.show_select_all_checkbox = False
        self.show_select_column = False
        self.pagesize = 999999
        request.set('disable_border', 1)
        self.context_actions = {}
        self.columns = {
            'id': {'title': _('Invoice Number')},
            'client': {'title': _('Client')},
            'invoicedate': {'title': _('Invoice Date')},
            'subtotal': {'title': _('Subtotal')},
            'vatamount': {'title': _('VAT')},
            'total': {'title': _('Total')},
        }
        self.review_states = [
            {
                'id': 'default',
                'contentFilter': {},
                'title': _('Default'),
                'transitions': [],
                'columns': [
                    'id',
                    'client',
                    'invoicedate',
                    'subtotal',
                    'vatamount',
                    'total',
                ],
            },
        ]

    def getInvoices(self, contentFilter):
        return self.context.objectValues('Invoice')

    def folderitems(self, full_objects=False):
        currency = currency_format(self.context, 'en')
        self.show_all = True
        self.contentsMethod = self.getInvoices
        items = BikaListingView.folderitems(self, full_objects)
        for item in items:
            obj = item['obj']
            number_link = "<a href='%s'>%s</a>" % (
                item['url'], obj.getId()
            )
            item['replace']['id'] = number_link
            item['client'] = obj.getClient().Title()
            item['invoicedate'] = self.ulocalized_time(obj.getInvoiceDate())
            item['subtotal'] = currency(obj.getSubtotal())
            item['vatamount'] = currency(obj.getVATAmount())
            item['total'] = currency(obj.getTotal())
        return items


class BatchFolderExportCSV(InvoiceBatchInvoicesView):
    def __call__(self, REQUEST, RESPONSE):
        """
        Export invoice batch into csv format.
        Writes the csv file into the RESPONSE to allow
        the file to be streamed to the user.
        Nothing gets returned.
        """

        delimiter = ','
        filename = 'invoice_batch.txt'
        # Getting the invoice batch
        container = self.context
        assert container
        container.plone_log("Exporting InvoiceBatch to CSV format for PASTEL")
        # Getting the invoice batch's invoices
        invoices = self.getInvoices({})
        if not len(invoices):
            container.plone_log("InvoiceBatch contains no entries")

        csv_rows = [
            # Invoice batch header
            ['Invoice Batch'],
            ['ID', container.getId()],
            ['Invoice Batch Title', container.title],
            ['Start Date', container.getBatchStartDate().strftime('%Y-%m-%d')],
            ['End Date', container.getBatchEndDate().strftime('%Y-%m-%d')],
            [],
            # Building the invoice field header
            ['Invoices'],
            ['Invoice ID', 'Client ID', 'Client Name', 'Account Num.', 'Phone',
             'Date', 'Total Price'],
        ]

        invoices_items_rows = []
        for invoice in invoices:
            # Building the invoice field header
            invoice_info_header = [invoice.getId(),
                                   invoice.getClient().getId(),
                                   invoice.getClient().getName(),
                                   invoice.getClient().getAccountNumber(),
                                   invoice.getClient().getPhone(),
                                   invoice.getInvoiceDate().strftime(
                                       '%Y-%m-%d'),
                                   invoice.getTotal(),
                                   ]
            csv_rows.append(invoice_info_header)
            # Obtaining and sorting all analysis items. These analysis are saved inside a list to add later
            items = invoice.invoice_lineitems
            mixed = [(item.get('OrderNumber', ''), item) for item in items]
            mixed.sort()
            # Defining each analysis row
            for line in mixed:
                invoice_analysis = [
                    line[1].get('ItemDate', '').strftime('%Y-%m-%d'),
                    line[1].get('ItemDescription', ''),
                    line[1].get('OrderNumber', ''),
                    line[1].get('Subtotal', ''),
                    line[1].get('VATAmount', ''),
                    line[1].get('Total', ''),
                ]
                invoices_items_rows.append(invoice_analysis)

        csv_rows.append([])
        # Creating analysis items header
        csv_rows.append(['Invoices items'])
        csv_rows.append(['Date', 'Description', 'Order', 'Amount', 'VAT',
                         'Amount incl. VAT'])
        # Adding all invoices items
        for item_row in invoices_items_rows:
            csv_rows.append(item_row)

        # convert lists to csv string
        ramdisk = StringIO()
        writer = csv.writer(ramdisk, delimiter=delimiter)
        assert writer
        writer.writerows(csv_rows)
        result = ramdisk.getvalue()
        ramdisk.close()
        # stream file to browser
        setheader = RESPONSE.setHeader
        setheader('Content-Length', len(result))
        setheader('Content-Type', 'text/x-comma-separated-values')
        setheader('Content-Disposition', 'inline; filename=%s' % filename)
        RESPONSE.write(result)


class PrintSummary(BrowserView):
    template = ViewPageTemplateFile("templates/invoicebatch_print_summary.pt")

    def getPreferredCurrencyAbreviation(self):
        return self.context.bika_setup.getCurrency()

    def items(self):
        currency = currency_format(self.context, 'en')
        return [{'id': obj.getId(),
                 'client': obj.getClient().Title(),
                 'invoicedate': self.ulocalized_time(obj.getInvoiceDate()),
                 'subtotal': currency(obj.getSubtotal()),
                 'vatamount': currency(obj.getVATAmount()),
                 'total': currency(obj.getTotal())}
                for obj in self.context.objectValues('Invoice')]

    def __call__(self):
        # Render the HTML which will be used to create the PDF.
        html = self.template()
        # createPdf returns PDF data
        data = createPdf(html)
        # So we let the browser deal with the PDF as it pleases.
        setheader = self.request.RESPONSE.setHeader
        setheader('Content-Type', 'application/pdf')
        self.request.RESPONSE.write(data)


class PrintAllInvoices(InvoiceView):
    template = ViewPageTemplateFile("templates/invoicebatch_print_all.pt")
    invoice_template = "templates/invoice_print.pt"

    def __init__(self, context, request):
        super(PrintAllInvoices, self).__init__(context, request)

    def __call__(self):
        """Render individual invoices with their own templates.  The output
        is stored in self.htmls, and output as a single PDF straight to the
        browser.
        """

        self.htmls = []
        for invoice in self.context.objectValues('Invoice'):
            self.invoice = invoice
            self.client = self.invoice.getClient()
            self.lineitems = self.get_lineitems()
            html = ViewPageTemplateFile(self.invoice_template)(self)
            self.htmls.append(html)

        # Render the HTML which will be used to create the PDF.
        html = self.template()

        # createPdf returns PDF data, but also writes it to the provided
        # outfile, so I'm going to ignore the returned data.
        data = createPdf(html)

        setheader = self.request.RESPONSE.setHeader
        setheader('Content-Type', 'application/pdf')
        self.request.RESPONSE.write(data)
