"""InvoiceBatch is a container for Invoice instances.
"""
from AccessControl import ClassSecurityInfo

from Products.CMFCore.utils import getToolByName
from Products.CMFPlone.utils import _createObjectByType
from bika.lims import bikaMessageFactory as _
from bika.lims.utils import t
from bika.lims.config import ManageInvoices, INVOICE_BATCH_TYPES, PROJECTNAME
from bika.lims.content.bikaschema import BikaSchema
from bika.lims.content.invoice import InvoiceLineItem
from bika.lims.interfaces import IInvoiceBatch
from DateTime import DateTime
from Products.Archetypes.public import *
from Products.CMFCore import permissions
from bika.lims.workflow import isBasicTransitionAllowed
from zope.container.contained import ContainerModifiedEvent
from zope.interface import implements

schema = BikaSchema.copy() + Schema((
    DateTimeField(
        'BatchStartDate',
        required=1,
        default_method='current_date',
        widget=CalendarWidget(
            label=_("Start Date"),
        ),
    ),
    DateTimeField(
        'BatchEndDate',
        required=1,
        default_method='current_date',
        widget=CalendarWidget(
            label=_("End Date"),
        ),
    ),
    StringField(
        'TypesToInvoice',
        vocabulary=INVOICE_BATCH_TYPES,
        default='analyses_orders',
        widget=SelectionWidget(
            format='radio',
            label=_('Object types invoiced'),
            description=_('Select which objects will be included '
                          'in these invoices.'),
        ),
    ),
),
)

schema['title'].default = DateTime().strftime('%B %Y')
# I allow duplicate titles here, because the same time period may include
# invoices for different types of objects.
schema['title'].validators = ()
# Update the validation layer after change the validator in runtime
schema['title']._validationLayer()


class InvoiceBatch(BaseFolder):
    """ Container for Invoice instances """
    implements(IInvoiceBatch)
    security = ClassSecurityInfo()
    displayContentsTab = False
    schema = schema

    _at_rename_after_creation = True

    def _renameAfterCreation(self, check_auto_id=False):
        from bika.lims.idserver import renameAfterCreation
        renameAfterCreation(self)

    security.declareProtected(ManageInvoices, 'invoices')

    def invoices(self):
        return self.objectValues('Invoice')

    security.declareProtected(ManageInvoices, 'createInvoice')

    def createInvoice(self, client_uid, items):
        """ Creates an invoice for a client and a set of items
        """
        lineitems = []
        for item in items:
            lineitem = InvoiceLineItem()
            if item.portal_type == 'AnalysisRequest':
                lineitem['ItemDate'] = item.getDatePublished()
                lineitem['OrderNumber'] = item.getRequestID()
                lineitem['AnalysisRequest'] = item.id
                lineitem['SupplyOrder'] = ''
            elif item.portal_type == 'SupplyOrder':
                lineitem['ItemDate'] = item.getDateDispatched()
                lineitem['OrderNumber'] = item.getOrderNumber()
                lineitem['AnalysisRequest'] = ''
                lineitem['SupplyOrder'] = item.id
            lineitem['Subtotal'] = item.getSubtotal()
            lineitem['VATAmount'] = item.getVATAmount()
            lineitem['Total'] = item.getTotal()
            lineitems.append(lineitem)
        invoice_id = self.generateUniqueId('Invoice')
        invoice = _createObjectByType("Invoice", self, invoice_id)
        invoice.edit(Client=client_uid, InvoiceDate=DateTime())
        invoice.processForm()
        invoice.invoice_lineitems = lineitems
        invoice.reindexObject()
        return invoice

    security.declarePublic('current_date')

    def current_date(self):
        """ return current date """
        return DateTime()

    def guard_cancel_transition(self):
        if not isBasicTransitionAllowed(self):
            return False
        return True

    def guard_reinstate_transition(self):
        if not isBasicTransitionAllowed(self):
            return False
        return True


registerType(InvoiceBatch, PROJECTNAME)


def ObjectModifiedEventHandler(instance, event):
    """ Various types need automation on edit.
    """
    bc = getToolByName(instance, 'bika_catalog')
    pc = getToolByName(instance, 'portal_catalog')
    if isinstance(event, ContainerModifiedEvent):
        # If item is substantively edited, we should re-calculate here.
        pass
    else:
        start = instance.getBatchStartDate()
        end = instance.getBatchEndDate()
        types = instance.getTypesToInvoice()
        brains = []
        if types == 'analyses' or types == 'analyses_orders':
            # Query for ARs in date range
            query = {
                'portal_type': 'AnalysisRequest',
                'review_state': 'published',
                'getInvoiceExclude': False,
                'getDatePublished': {
                    'range': 'min:max',
                    'query': [start, end]
                }
            }
            brains.extend(bc(query))
        if types == 'orders' or types == 'analyses_orders':
            # Query for Orders in date range
            query = {
                'portal_type': 'SupplyOrder',
                'review_state': 'dispatched',
                'getDateDispatched': {
                    'range': 'min:max',
                    'query': [start, end]
                }
            }
            brains.extend(pc(query))
        # Make list of clients from found ARs and Orders
        clients = {}
        for brain in brains:
            obj = brain.getObject()
            key = obj.aq_parent.Title() + "__" + obj.aq_parent.UID()
            if key not in clients:
                clients[key] = []
            clients[key].append(obj)
        keys = clients.keys()
        keys.sort()
        # Create an invoice for each client
        for key in keys:
            items = clients[key]
            uid = key.split("__")[-1]
            instance.createInvoice(uid, items)
