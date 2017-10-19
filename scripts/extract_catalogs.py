#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""Genera un data.json a partir de un catálogo en excel.
"""

from __future__ import unicode_literals
from __future__ import print_function
from __future__ import with_statement
import os
import sys
import StringIO
import yaml
import requests
import pandas as pd
import arrow
import logging
from openpyxl import load_workbook
from pydatajson import DataJson
import pydatajson.readers as readers
import pydatajson.writers as writers

from helpers import get_logger, ensure_dir_exists
from paths import SCHEMAS_DIR, REPORTES_DIR, BACKUP_CATALOG_DIR, CATALOGS_DIR
from paths import CATALOGS_INDEX_PATH

sys.path.insert(0, os.path.abspath(".."))


NOW = arrow.now().isoformat()
TODAY = arrow.now().format('YYYY-MM-DD')


def read_xlsx_catalog(catalog_xlsx_path, logger=None):
    """Lee catálogo en excel."""

    default_values = {
        "catalog_modified": NOW,
        "dataset_issued": NOW,
        "distribution_issued": NOW,
        "dataset_modified": NOW,
        "distribution_modified": NOW
    }

    catalogo = readers.read_xlsx_catalog(catalog_xlsx_path, logger)
    catalogo = DataJson(catalogo, default_values=default_values)

    clean_catalog(catalogo)

    return catalogo


def clean_catalog(catalog):

    for dataset in catalog["dataset"]:
        for distribution in dataset["distribution"]:
            if "field" in distribution:
                for field in distribution["field"]:
                    if "title" in field:
                        field["title"] = field["title"].replace(" ", "")
                    if "id" in field:
                        field["id"] = field["id"].replace(" ", "")


def write_json_catalog(catalog_id, catalog, catalog_json_path):
    """Escribe catálogo en JSON y guarda una copia con fecha."""
    catalog_backup_json_path = os.path.join(
        BACKUP_CATALOG_DIR, catalog_id, "data-{}.json".format(TODAY))

    # crea los directorios necesarios
    ensure_dir_exists(os.path.dirname(catalog_json_path))
    ensure_dir_exists(os.path.dirname(catalog_backup_json_path))

    writers.write_json_catalog(catalog, catalog_json_path)
    writers.write_json_catalog(catalog, catalog_backup_json_path)


def validate_and_filter(catalog_id, catalog, warnings_log):
    """Valida y filtra un catálogo en data.json."""
    dj = DataJson(catalog,
                  schema_filename="catalog.json", schema_dir=SCHEMAS_DIR)

    # valida todo el catálogo para saber si está ok
    is_valid_catalog = dj.is_valid_catalog()
    logging.info(
        "Metadata a nivel de catálogo es válida? {}".format(is_valid_catalog))

    # genera directorio de reportes para el catálogo
    reportes_catalog_dir = os.path.join(REPORTES_DIR, catalog_id)
    ensure_dir_exists(reportes_catalog_dir)

    # genera reporte de validación completo
    dj.validate_catalog(
        only_errors=True, fmt="list",
        export_path=os.path.join(reportes_catalog_dir,
                                 "reporte-catalogo-errores.xlsx")
    )

    # genera reporte de datasets para federación
    dj.generate_datasets_report(
        catalog, harvest='valid',
        export_path=os.path.join(reportes_catalog_dir, "reporte-datasets.xlsx")
    )

    # genera mensaje de reporte
    subject, message = generate_validation_message(
        catalog_id, is_valid_catalog, warnings_log)

    with open(os.path.join(reportes_catalog_dir,
                           "extraction_mail_subject.txt"), "wb") as f:
        f.write(subject.encode("utf-8"))
    with open(os.path.join(reportes_catalog_dir,
                           "extraction_mail_message.txt"), "wb") as f:
        f.write(message.encode("utf-8"))

    # genera catálogo filtrado por los datasets que no tienen error
    catalog_filtered = dj.generate_harvestable_catalogs(
        catalog, harvest='valid')[0]

    return catalog_filtered


def generate_validation_message(catalog_id, is_valid_catalog, warnings_log):
    """Genera asunto y mensaje del mail de reporte a partir de indicadores.

    Args:
        catalog_id (str): Identificador del catálogo
        is_valid_catalog (bool): Indica si el catálogo está libre de errores.

    Return:
        tuple: (str, str) (asunto, mensaje)
    """
    server_environment = os.environ.get("SERVER_ENVIRONMENT", "desconocido")

    # asunto del mail
    subject = "[{}] Validacion de catalogo '{}': {}".format(
        server_environment,
        catalog_id,
        arrow.now().format("DD/MM/YYYY HH:mm")
    )

    # mensaje del mail
    warnings_str = warnings_log.getvalue()
    if is_valid_catalog and len(warnings_str) == 0:
        message = "El catálogo '{}' no tiene errores.".format(catalog_id)
    else:
        message = "El catálogo '{}' tiene errores.".format(catalog_id)
        message += "\n{}".format(warnings_str)

    return subject, message


def process_catalog(catalog_id, catalog_format, catalog_url,
                    catalogs_dir=CATALOGS_DIR):
    """Descarga y procesa el catálogo.

    Transforma catálogos en distintos formatos a data.json, valida y actualiza
    algunos campos de metadatos y emite informes a los administradores.

    Args:
        catalog_id (str): Identificador del catálogo.
        catalog_format (str): Uno de "xlsx", "json" o "ckan".
        catalog_url (str): Url pública desde donde descargar el catálogo.
        catalogs_dir (str): Directorio local donde se descargan los catálogos.
    """
    logger = get_logger(__name__)

    # loggea warnings en un objeto para el mensaje de reporte
    warnings_log = StringIO.StringIO()
    fh = logging.StreamHandler(warnings_log)
    fh.setLevel(logging.WARNING)
    logger.addHandler(fh)

    # crea directorio y template de path al catálogo y reportes
    catalog_dir = os.path.join(catalogs_dir, catalog_id)
    ensure_dir_exists(catalog_dir)
    catalog_path_template = os.path.join(catalog_dir, "{}")

    # procesa el catálogo dependiendo del formato
    logger.info('=== Catálogo {} ==='.format(catalog_id.upper()))
    try:
        logger.info('- Descarga y lectura de catálogo')
        if catalog_format.lower() == 'xlsx':

            # descarga del catálogo
            res = requests.get(catalog_url, verify=False)
            catalog_xlsx_path = catalog_path_template.format("catalog.xlsx")
            with open(catalog_xlsx_path, 'w') as f:
                f.write(res.content)

            logger.info('- Transformación de XLSX a JSON')
            catalog = read_xlsx_catalog(catalog_xlsx_path, logger)

        elif catalog_format.lower() == 'json':
            logger.info('- Lectura directa de JSON')
            catalog = DataJson(catalog_url)

        elif catalog_format.lower() == 'ckan':
            logger.info('- Transformación de CKAN API a JSON')
            catalog = read_ckan_catalog(catalog_url)

        else:
            raise ValueError(
                '{} no es una extension valida para un catalogo.'.format(
                    file_ext))

        # filtra, valida y escribe el catálogo en JSON y XLSX
        if catalog and len(catalog) > 0:
            logger.info("- Valida y filtra el catálogo")
            catalog_filtered = validate_and_filter(catalog_id, catalog,
                                                   warnings_log)

            logger.info("- Setea el draft status de todas las distribuciones")
            for distribution in catalog.get_distributions():
                distribution["draft"] = False

            logger.info('- Escritura de catálogo en JSON')
            write_json_catalog(
                catalog_id, catalog_filtered,
                catalog_path_template.format("data.json"))

            # logger.info('- Escritura de catálogo en XLSX')
            # writers.write_xlsx_catalog(
            # catalog_filtered, catalog_path_template.format("catalog.xlsx"))
        else:
            raise Exception("El catálogo {} no se pudo generar".format(
                catalog_id))

        # genera reportes del catálogo
        # logger.info('- Generación de reportes')
        # catalog_filtered.generate_catalog_readme(
        #     catalog_filtered,
        #     export_path=catalog_path_template.format('README.md'))
        # catalog_filtered.generate_datasets_summary(
        #     catalog_filtered,
        #     export_path=catalog_path_template.format('datasets.csv'))

    except Exception as e:
        logger.error(
            'Error al procesar el catálogo de {}'.format(catalog_id),
            exc_info=True)


def main(catalogs_index_path=CATALOGS_INDEX_PATH, catalogs_dir=CATALOGS_DIR):
    logger = get_logger(__name__)

    logger.info('>>> COMIENZO DE LA EXTRACCION DE CATALOGOS <<<')

    # cargo los parámetros de los catálogos a extraer
    with open(catalogs_index_path) as config_file:
        catalogs_index = yaml.load(config_file)

    # procesa los catálogos
    for catalog_id in catalogs_index:
        process_catalog(
            catalog_id,
            catalogs_index[catalog_id]["formato"],
            catalogs_index[catalog_id]["url"],
            catalogs_dir
        )

    logger.info('>>> FIN DE LA EXTRACCION DE CATALOGOS <<<')


if __name__ == '__main__':
    main(sys.argv[1], sys.argv[2])
