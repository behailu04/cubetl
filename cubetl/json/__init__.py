import logging
from os import listdir
from os.path import isfile, join
import itertools
import re
from cubetl.core import Node
import chardet
from BeautifulSoup import UnicodeDammit
from cubetl.fs import FileReader, FileWriter
import csv
import StringIO
import json



# Get an instance of a logger
logger = logging.getLogger(__name__)


class JsonReader(Node):

    name = None
    data = '${ m["data"] }'
    iterate = True  # only if is an array

    def process(self, ctx, m):

        logger.debug("Processing JSON data at %s" % self)

        # Resolve data
        data = ctx.interpolate(m, self.data)

        result = json.loads(data)
        if isinstance(result, list):
            for item in result:
                m2 = ctx.copy_message(m)
                if self.name:
                    m2[self.name] = item
                else:
                    if not isinstance(item, dict):
                        raise Exception("Cannot merge a non dictionary value (%s) with current message in %s (use 'name' to assign the object to a message property)" % (str(item), self))
                    m2.extend(item)
                yield m2
        else:
            if self.name:
                m[self.name] = result
            else:
                if not isinstance(item, dict):
                    raise Exception("Cannot merge a non dictionary value (%s) with current message in %s (use 'name' to assign the object to a message property)" % (str(item), self))
                m.extend(item)
            yield m


class JsonFileReader (JsonReader):
    """
    This class is a shortcut to a FileReader and JsonReader
    """

    # TODO: This and CSVFileReader should possibly extend FileReader (in streaming mode, if appropriate)

    data = '${ m["_jsondata"] }'
    path = None

    def initialize(self, ctx):

        super(JsonFileReader, self).initialize(ctx)

        self._fileReader = FileReader()
        self._fileReader.path = self.path
        self._fileReader.name = "_jsondata"
        self._fileReader.encoding = None
        self.data = '${ m["_jsondata"] }'
        ctx.comp.initialize(self._fileReader)

    def finalize(self, ctx):
        ctx.comp.finalize(self._fileReader)
        super(JsonFileReader, self).finalize(ctx)

    def process(self, ctx, m):

        logger.debug("Reading and processing JSON file %s at %s" % (self.path, self))

        file_msg = ctx.comp.process(self._fileReader, m)
        for mf in file_msg:
            m2 = ctx.copy_message(m)
            json_rows = super(JsonFileReader, self).process(ctx, m2)
            for json_row in json_rows:
                del(json_row['_jsondata'])
                yield json_row


class JsonFileWriter(FileWriter):

    data = '${ m }'
    fields = None
    multiple = True
    sort_keys = True
    indent = 4
    _count = 0

    def initialize(self, ctx):
        super(JsonFileWriter, self).initialize(ctx)
        self.newline = False

    def finalize(self, ctx):
        super(JsonFileWriter, self).finalize(ctx)

    def _csv_row(self, ctx, row):

        if self.encoding:
            row = [(r.encode(self.encoding) if isinstance(r, basestring) else r) for r in row]

        self._csvwriter.writerow(row)
        result = self._output.getvalue()
        self._output.truncate(0)
        return result

    def on_open(self):
        if (self.multiple):
            self._open_file.write("[")

    def on_close(self):
        if (self.multiple):
            self._open_file.write("]")

    def process(self, ctx, m):

        self._count = self._count + 1

        data = ctx.interpolate(m, self.data)

        if self.fields:
            o = {}
            for f in self.fields:
                o[f] = data[f]
        else:
            o = data

        value = json.dumps(o, sort_keys = self.sort_keys, indent = self.indent) # ensure_ascii, check_circular, allow_nan, cls, separators, encoding, default, )
        if (self.multiple and self._count > 1):
            value = ", " + value
        super(JsonFileWriter, self).process(ctx, m, value)

        yield m



