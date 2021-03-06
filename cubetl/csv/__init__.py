# CubETL
# Copyright (c) 2013-2019 Jose Juan Montes

# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:

# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.

# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.

from os import listdir
from os.path import isfile, join
import io
import csv
import itertools
import logging

from cubetl.core import Node
from cubetl.core.exceptions import ETLException
from cubetl.fs import FileReader, FileWriter
import chardet
import re


# Get an instance of a logger
logger = logging.getLogger(__name__)


class CsvReader(Node):

    def __init__(self):
        super().__init__()

        self.data = '${ m["data"] }'

        self.headers = None

        self.comment = None
        self.delimiter = ","
        self.row_delimiter = "\n"
        self.ignore_missing = False
        self.strip = False

        self.count = 0
        self._linenumber = 0


    '''
    def _utf_8_encoder(self, unicode_csv_data):
        for line in unicode_csv_data:
            yield line
            #yield line.encoes()de('utf-8')
    '''

    def process(self, ctx, m):

        logger.debug("Processing CSV data at %s" % self)

        # Resolve data
        data = ctx.interpolate(self.data, m)

        header = None
        if (self.headers):
            if (isinstance(self.headers, str)):
                header = [h.strip() for h in self.headers.split(",")]
            else:
                header = self.headers

        self._linenumber = 0
        rows = iter(data.split(self.row_delimiter))
        #if self.strip:
        #    rows = [r.strip() for r in rows]

        reader = csv.reader(rows, delimiter=self.delimiter, skipinitialspace=self.strip, doublequote=True, quotechar='"')
        for row in reader:

            # Skip empty lines
            if (len(row) == 1 and not row[0].strip()) or len(row) == 0:
                continue

            # Skip lines with comments if so configured
            if (self.comment and row[0].startswith(self.comment)):
                continue

            # Load header if not defined already
            if header is None:
                header = [v for v in row]
                logger.debug("CSV header is: %s" % header)
                continue

            #if (self._linenumber == 0) and (self.header): continue

            self._linenumber = self._linenumber + 1

            #arow = {}
            if (len(row) > 0):
                try:
                    arow = ctx.copy_message(m)
                    for header_index in range(0, len(header)):
                        if header_index < len(row) or not self.ignore_missing:
                            # arow[(header[header_index])] = str(row[header_index], "utf-8")
                            value = row[header_index]
                            if self.strip:
                                value = value.strip()
                            arow[header[header_index]] = value
                except Exception as e:
                    logger.error("Could not process CSV data (%r) at %s: %s" % (row, self, e))
                    raise ETLException("Could not process CSV data (%r) at %s: %s" % (row, self, e))

                    self.count = self.count + 1
                    arow['_csv_count'] = self.count
                    arow['_csv_linenumber'] = self._linenumber

                yield arow


class CsvFileReader (CsvReader):
    """
    This class is a shortcut to a FileReader and CsvReader
    """

    # TODO: This shall be a FileLineReader?

    path = None

    encoding = "detect"
    encoding_errors = "strict" # strict, ignore, replace
    encoding_abort = True

    def initialize(self, ctx):

        super(CsvFileReader, self).initialize(ctx)

        self._fileReader = FileReader()
        self._fileReader.path = self.path
        if (self.encoding):
            self._fileReader.encoding = self.encoding

        ctx.comp.initialize(self._fileReader)

    def finalize(self, ctx):
        ctx.comp.finalize(self._fileReader)
        super(CsvFileReader, self).finalize(ctx)

    def process(self, ctx, m):

        logger.debug("Reading and processing CSV file at %s" % self)

        files_msgs = ctx.comp.process(self._fileReader, m)
        for mf in files_msgs:
            csv_rows = super(CsvFileReader, self).process(ctx, m)
            for csv_row in csv_rows:
                yield csv_row


class CsvFileWriter(Node):
    """
    This node writes message attributes
    """

    # TODO: columns should be a CubETL type (as SQLColumns, etc). We could use
    # cubetl.table TableColumns here, which in the end are basic mappings
    # with name, label, value/eval (and maybe default and/or type...)

    # TODO: This class should possibly compose FileWriter and CsvWriter
    # (a CSVWriter should be able to write CSV rows to messages)

    def __init__(self, path="-", overwrite=False):
        super().__init__()

        self.data = '${ m }'
        self.headers = None
        self.write_headers = True
        self.path = path

        self.delimiter = ","
        self.row_delimiter = "\n"

        self.overwrite = overwrite
        self.encoding = None #"utf-8"

        self.columns = None
        self.auto_columns = True

        self._row = 0
        self._output = None
        self._csvwriter = None

    def initialize(self, ctx):

        super(CsvFileWriter, self).initialize(ctx)

        self._fileWriter = FileWriter(path=self.path,
                                      data="${ m['_csvdata'] }",
                                      newline=False,
                                      overwrite=self.overwrite)
        if (self.encoding):
            self._fileWriter.encoding = self.encoding

        ctx.comp.initialize(self._fileWriter)

    def initialize_columns(self):

        for c in self.columns:
            if "label" not in c:
                c["label"] = c["name"]
            if "value" not in c:
                c["value"] = '${ m["' + c["name"] + '"] }'

    def columns_from_message(self, ctx, m):
        self.columns = []
        for k, v in m.items():
            column = {'name': k}
            self.columns.append(column)

        # Sort by name for repeatable results
        self.columns.sort(key=lambda c: c['name'])

    def finalize(self, ctx):
        ctx.comp.finalize(self._fileWriter)
        super(CsvFileWriter, self).finalize(ctx)

    def _csv_row(self, ctx, row):

        if self.encoding:
            row = [(r.encode(self.encoding) if isinstance(r, str) else r) for r in row]

        self._csvwriter.writerow(row)
        result = self._output.getvalue()
        self._output.truncate(0)
        self._output.seek(0)
        return result

    def process(self, ctx, m):

        if not self._csvwriter:
            self._output = io.StringIO()
            self._csvwriter = csv.writer(self._output, delimiter=self.delimiter,
                                         quotechar='"', quoting=csv.QUOTE_MINIMAL)

        if (self._row == 0):

            # Process columns
            if self.columns is None and self.auto_columns and m:
                self.columns_from_message(ctx, m)

            self.initialize_columns()

            # Write headers
            if (self.write_headers):
                row = [c["label"] for c in self.columns]
                m['_csvdata'] = self._csv_row(ctx, row)
                self._fileWriter.process(ctx, m)

        self._row = self._row + 1

        row = [ctx.interpolate(c["value"], m) for c in self.columns]
        m['_csvdata'] = self._csv_row(ctx, row)
        self._fileWriter.process(ctx, m)
        del (m['_csvdata'])

        yield m



