import xlseries.strategies.get.data
import collections


class BaseGetDataStrategy(xlseries.strategies.get.data.BaseGetDataStrategy):

    def _get_values(self, ws, params):
        p = params
        # create iterator of values
        iter_values = self._values_iterator(ws, p["alignment"],
                                            p["headers_coord"],
                                            p["data_starts"],
                                            p["data_ends"])

        values_dict = collections.OrderedDict()
        for value, index in iter_values:
            try:
                new_value = self._handle_new_value(list(values_dict.values()), value,
                                                   p["missings"],
                                                   p["missing_value"],
                                                   p["blank_rows"])
            except Exception as e:
                raise Exception(
                    "Error {} parsing data from Title: '{}' - Head: '{}' - Index: '{}'".format(
                        e, ws.title, p['headers_coord'], index
                    )
                )

            if self._value_to_be_added(new_value, index, ws, p):
                frequency = self._get_frequency(p["frequency"])
                if frequency not in values_dict:
                    values_dict[frequency] = []
                values_dict[frequency].append(new_value)

        # fill the missing values if they are implicit
        # it doesn't work with multifrequency series
        if (p["missings"] and "Implicit" in p["missing_value"] and
                len(p["frequency"]) == 1):
            values = list(values_dict.values())[0]
            values = self._fill_implicit_missings(ws,
                                                  values,
                                                  p["frequency"],
                                                  p["time_header_coord"],
                                                  p["data_starts"],
                                                  p["data_ends"],
                                                  p["alignment"])
            return [values]

        return list(values_dict.values())


class BaseSingleFrequency(xlseries.strategies.get.data.BaseSingleFrequency):
    pass


class BaseMultiFrequency(xlseries.strategies.get.data.BaseMultiFrequency):
    pass


class BaseContinuous(xlseries.strategies.get.data.BaseContinuous):
    pass


class BaseNonContinuous(xlseries.strategies.get.data.BaseNonContinuous):
    pass


class BaseAccepts(xlseries.strategies.get.data.BaseAccepts):

    @classmethod
    def _base_cond(cls, ws, params):
        """Check that all base classes accept the input."""
        for base in cls.__bases__:
            if (
                    base is not BaseGetDataStrategy and
                    (hasattr(base, "_accepts") and not base._accepts(ws, params))
            ):
                return False
        return True


def get_strategies():
    custom = xlseries.utils.strategies_helpers.get_strategies()

    combinations = []
    for freq in [BaseSingleFrequency, BaseMultiFrequency]:
        for cont in [BaseContinuous, BaseNonContinuous]:

            name = freq.__name__ + cont.__name__
            bases = (BaseAccepts, freq, cont, BaseGetDataStrategy)
            parser = type(name, bases, {})

            combinations.append(parser)

    return custom + combinations