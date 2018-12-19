import logging
import cubetl
from copy import deepcopy
from cubetl.core.exceptions import ETLConfigurationException
import inspect

# Get an instance of a logger
logger = logging.getLogger(__name__)


class Component(object):
    """
    Base class for all components.
    """

    def __init__(self):
        self.ctx = None
        self.urn = None

    def initialize(self, ctx):
        if hasattr(self, '_initialized'):
            raise ETLConfigurationException("Component already initialized: %s" % self)
        self._initialized = True
        self.ctx = ctx

    def finalize(self, ctx):
        #self.ctx = None
        pass

    def __str__(self, *args, **kwargs):
        return "%s(%s)" % (self.__class__.__name__, self.urn)

    def __repr__(self):
        args = []
        argspec = inspect.getargspec(self.__init__)  # ArgSpec(args=['self', 'name'], varargs=None, keywords=None, defaults=None)
        #print(argspec)
        for key in argspec.args:
            if key == "self": continue
            value = getattr(self, key) if hasattr(self, key) else None

            if value and isinstance(value, Component):
                value = "ctx.get('%s')" % value.urn
            else:
                value = "%r" % (value)

            args.append((key, value))  # TODO: get default?
        '''
        if argspec.keywords:
            for key in argspec.keywords:
                print(argspec.keywords)
                print(argspec.defaults)
                if not hasattr(self, key): continue
                args.append((key, getattr(self, key)))  # TODO: get default?
        '''
        return "%s(%s)" % (self.__class__.__name__, ", ".join(["%s=%s" % (key, value) for key, value in args]))


class Node(Component):
    """
    Base class for all control flow nodes.

    These must implement a process(ctx, m) method that
    accepts and yield messages.
    """

    def process(self, ctx, m):

        yield m


class ContextProperties(Component):

    #def after_properties_set(self):

    def load_properties(self, ctx):

        for attr in self.__dict__:

            if (attr == "id"):
                continue

            value = getattr(self, attr)
            value = ctx.interpolate(None, value)

            if attr not in ctx.props:
                logger.debug("Setting context property %s = %s" % (attr, value))
                ctx.props[attr] = value
            else:
                logger.debug("Not setting context property %s as it is already defined with value %s" % (attr, ctx.props[attr]))


class Mappings(Component):
    """
    Serves as a holder for mappings, which can be included from other mappings.

    This component tries to make mappings more reusable, by providing a way to reference
    them.
    """

    mappings = None

    def initialize(self, ctx):

        #raise Exception("Mappings initialize method cannot be called.")

        super(Mappings, self).initialize(ctx)
        Mappings.includes(ctx, self.mappings)

    def finalize(self, ctx):

        #raise Exception("Mappings finalize method cannot be called.")
        super(Mappings, self).finalize(ctx)


    @staticmethod
    def includes(ctx, mappings):

        mapping = True
        while mapping != None:
            pos = 0
            mapping = None
            for m in mappings:
                if (isinstance(m, Mappings)):
                    mapping = m
                    break
                else:
                    pos = pos + 1

            if (mapping):
                # It's critical to copy mappings
                ctx.comp.initialize(mapping)
                mappings[pos:pos + 1] = deepcopy(mapping.mappings)

