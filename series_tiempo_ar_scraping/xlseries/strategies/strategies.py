from xlseries.strategies import strategies
from ..strategies.get.data import get_strategies

import pandas as pd
import numpy as np


class ParameterDiscovery(strategies.ParameterDiscovery):

    @classmethod
    def _get_data(cls, ws, params):
        """Parse data using parameters and return it in data frames."""
        # import pdb; pdb.set_trace()
        # 1. Build data frames dict based on number of period ranges founded
        dfs_dict = {}
        for period_range in cls._get_period_ranges(ws, params):
            hashable_pr = cls._hash_period_range(period_range)
            if hashable_pr not in dfs_dict:
                dfs_dict[hashable_pr] = {"columns": [], "data": [],
                                         "period_range": period_range}

        # 2. Get name (column) and values of each data series
        for i_series in range(len(params.headers_coord)):

            # iterate strategies looking for someone that accepts it
            params_series = params[i_series]
            name, values = None, None
            for strategy in get_strategies():

                if strategy.accepts(ws, params_series):
                    strategy_obj = strategy()
                    # import pdb; pdb.set_trace()
                    names_and_values = strategy_obj.get_data(ws, params_series)
                    names, values = names_and_values[0]
                    break

            # raise exception if no strategy accepts the input
            if not names_and_values:
                msg = "There is no strategy to deal with " + str(params_series)
                raise Exception(msg)

            if (params_series["time_multicolumn"] and
                    isinstance(params_series["time_header_coord"], list)):
                time_header_coord = params_series["time_header_coord"][0]
            else:
                time_header_coord = params_series["time_header_coord"]

            prs = cls._get_series_prs(ws, params_series["frequency"],
                                      params_series["data_starts"],
                                      time_header_coord,
                                      params_series["data_ends"],
                                      params_series["time_alignment"],
                                      params_series["alignment"])

            for period_range, (name, values) in zip(prs, names_and_values):
                hashable_pr = cls._hash_period_range(period_range)

                cls._add_name(name, dfs_dict[hashable_pr]["columns"])
                dfs_dict[hashable_pr]["data"].append(values)

        # 3. Build data frames
        dfs = []
        for df_inputs in list(dfs_dict.values()):

            period_range = df_inputs["period_range"]
            columns = df_inputs["columns"]
            data = np.array(df_inputs["data"]).transpose()

            # try with business days if daily frequency fails
            if period_range.freqstr == "D":
                try:
                    df = pd.DataFrame(index=period_range,
                                      columns=columns,
                                      data=data)
                except ValueError:
                    # rework period range in business days
                    pr = period_range
                    ini_date = "{}-{}-{}".format(pr[0].year,
                                                 pr[0].month, pr[0].day)
                    end_date = "{}-{}-{}".format(pr[-1].year,
                                                 pr[-1].month, pr[-1].day)
                    pr_B = pd.period_range(ini_date, end_date, freq="B")

                    df = pd.DataFrame(index=pr_B,
                                      columns=columns,
                                      data=data)

            # go straight if frequency is not daily
            else:
                df = pd.DataFrame(index=period_range,
                                  columns=columns,
                                  data=data)

            dfs.append(df)

        return dfs
