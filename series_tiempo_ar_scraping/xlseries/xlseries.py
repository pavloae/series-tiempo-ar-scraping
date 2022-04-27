import xlseries
from xlseries.strategies import strategies
from xlseries.utils.xl_methods import make_wb_copy
from .strategies.strategies import ParameterDiscovery


class XlSeries(xlseries.XlSeries):

    def get_data_frames(self, params_path_or_obj, ws_name=None, safe_mode=False, preserve_wb_obj=True):
        """Scrape time series from an excel file into a pandas.DataFrame.

                Args:
                    params_path_or_obj (str, dict or Parameters): Scraping parameters.
                        str: Path to a JSON file with parameters.
                        dict: Python dictionary with parameters like
                        Parameters: A Parameters object already built.

                    ws_name (str): Name of the worksheet that will be scraped.

                    safe_mode (bool): When some parameters are not passed by the user,
                        the safe mode will check all possible combinations, returning
                        more than one result if many are found. If safe_mode is set to
                        False, the first succesful result will be returned without
                        checking the other possible combinations of parameters.

                    preserve_wb_obj (bool): If True makes a safe copy of a workbook to
                        preserve the original object without changes. Only use False if
                        changes to the workbook object are not a problem.

                Returns:
                    list: A list of pandas.DataFrame objects with time series scraped
                        from the excel file. Every DataFrame in the list corresponds to
                        a different frequency.

                Example:
                    params = {"headers_coord": ["B1","C1"],
                              "data_starts": 2,
                              "frequency": "M",
                              "time_header_coord": "A1"}
                    dfs = XlSeries(wb).get_data_frames(params)

                """
        # wb will be changed, so it has to be a copy to preserve the original
        if preserve_wb_obj:
            wb_copy = make_wb_copy(self.wb)
        else:
            wb_copy = self.wb
        ws_names = wb_copy.sheetnames

        if not ws_name:
            ws_name = ws_names[0]
            if len(ws_names) > 1:
                msg = "There are {} worksheets: {}\nThe first {} will be " + \
                      "analyzed"
                print(msg.format(len(ws_names),
                                 str([name.encode("utf-8")
                                      for name in ws_names]),
                                 ws_name.encode("utf-8")))
                print("Remember you can choose a different one passing a " +
                      "ws_name keyword argument.")
        else:
            ws_name = self._sanitize_ws_name(ws_name, ws_names)

        for scraper in strategies.get_strategies():
            if scraper.accepts(wb_copy):

                # Override by custom class to allow modify exception message
                if scraper.__name__ == 'ParameterDiscovery':
                    scraper = ParameterDiscovery

                scraper_obj = scraper(wb_copy, params_path_or_obj, ws_name)
                dfs, params = scraper_obj.get_data_frames(safe_mode)
                self.params[ws_name] = params

                if isinstance(dfs, list) and len(dfs) == 1:
                    return dfs[0]
                else:
                    return dfs
