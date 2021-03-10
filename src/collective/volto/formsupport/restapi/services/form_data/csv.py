# -*- coding: utf-8 -*-
from collective.volto.formsupport.interfaces import IFormDataStore
from plone.restapi.serializer.converters import json_compatible
from plone.restapi.services import Service
from six import StringIO
from zope.component import getMultiAdapter

import csv
import six


class FormDataExportGet(Service):
    def render(self):
        self.check_permission()

        self.request.response.setHeader(
            "Content-Disposition",
            'attachment; filename="{0}.csv"'.format(self.__name__),
        )
        self.request.response.setHeader(
            "Content-Type", "text/comma-separated-values"
        )

        data = self.get_data()
        if isinstance(data, six.text_type):
            data = data.encode("utf-8")
        self.request.response.write(data)

    def get_data(self):
        store = getMultiAdapter((self.context, self.request), IFormDataStore)
        sbuf = StringIO()

        columns = []

        rows = []
        for item in store.search():
            data = {}
            for k, v in item.attrs.items():
                if k not in columns:
                    columns.append(k)
                data[k] = json_compatible(v)
            rows.append(data)

        writer = csv.DictWriter(sbuf, fieldnames=columns, delimiter=",")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)
        res = sbuf.getvalue()
        sbuf.close()
        return res
