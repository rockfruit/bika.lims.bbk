from bika.lims.interfaces import IFieldIcons
from zope.interface import implements

class PriorityIcons(object):

    """An icon provider for indicating AR priorities
    """

    implements(IFieldIcons)

    def __init__(self, context):
        self.context = context

    def __call__(self, **kwargs):
        if not hasattr(self.context, 'getPriority'):
            return {}
        priority = self.context.getPriority()
        if priority and hasattr(priority, 'portal_type') and priority.portal_type == 'ARPriority':
            result = {
                'msg': priority.Title(),
                'field': 'Priority',
                'icon': '',
            }
            icon = priority.getSmallIcon()
            if icon:
                result['icon'] = '/'.join(icon.getPhysicalPath())
            return {self.context.UID(): [result]}
        return {}

