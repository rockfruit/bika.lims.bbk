from bika.lims.browser import BrowserView
from bika.lims.interfaces import IInvoiceView
from Products.CMFCore.utils import getToolByName
from Products.Five.browser.pagetemplatefile import ViewPageTemplateFile
from zope.i18n.locales import locales
from zope.interface import implements


class InvoiceView(BrowserView):
    implements(IInvoiceView)

    template = ViewPageTemplateFile("templates/invoice.pt")

    def __init__(self, context, request, invoice=None):
        super(InvoiceView, self).__init__(context, request)
        self.invoice = invoice if invoice else context
        locale = locales.getLocale('en')
        self.currency = self.context.bika_setup.getCurrency()
        self.symbol = locale.numbers.currencies[self.currency].symbol
        request.set('disable_border', 1)

    def client_address(self):
        rawaddress = self.client.getBillingAddress() \
                     or self.client.getPostalAddress() \
                     or self.client.getPhysicalAddress()
        if rawaddress.get('address', False):
            return "<div>%s</div>" % rawaddress['address'] + \
                   "<div>%s %s</div>" % (rawaddress['city'],
                                         rawaddress['zip']) + \
                   "<div>%s</div>" % rawaddress['state'] + \
                   "<div>%s</div>" % rawaddress['country']
        return ""

    def get_lineitems(self):
        # A list with the items and its invoice values to render in template
        # Gather the line items
        items = []
        for item in self.invoice.invoice_lineitems:
            invoice_data = {
                'invoiceDate': self.ulocalized_time(item.get('ItemDate', '')),
                'description': item.get('ItemDescription', ''),
                'orderNo': item.get('OrderNumber', ''),
                'Subtotal': "%.02f"%(float(item.get('Subtotal', '0'))),
                'VATAmount': "%.02f"%(float(item.get('VATAmount', '0'))),
                'Total': "%.02f"%(float(item.get('Total', '0'))),
            }
            url = ''
            if item.get('AnalysisRequest', False):
                url = item['AnalysisRequest'].absolute_url()
            elif item.get('SupplyOrder', ''):
                url = item['SupplyOrder'].absolute_url()
            invoice_data['orderNoURL'] = url
            items.append(invoice_data)
        return items


    def __call__(self):
        self.client = self.invoice.getClient()

        # Render the template
        self.lineitems = self.get_lineitems()
        return self.template()


class InvoicePrintView(InvoiceView):
    template = ViewPageTemplateFile("templates/invoice_print.pt")

    def __call__(self):
        return InvoiceView.__call__(self)
