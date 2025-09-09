from __future__ import annotations

import logging

from pypeh.core.interfaces.outbound.export import ExportInterface

logger = logging.getLogger(__name__)

ANALYTICALINFO_EXCLUSION_LIST = [
    "id_subject",
    "matrix",
    "analysisyear",
    "analysismonth",
    "analysisday",
    "density",
    "osm",
    "sg",
    "uvolume",
    "lipid_enz",
]
ANALYTICALINFO_MATRIX_TRANSLATION = {
    "urine_lab": "US;UM",
    "bloodserum_lab": "BS",
    "bloodwholeblood_lab": "BWB",
    "hair_lab": "H",
}

DATATYPE_TRANSLATION_DICT = {
    "string": "varchar",
    "number": "decimal",
    "boolean": "bool",
    "datetime": "datetime",
}


def get_observable_property_property(varname, observable_property, codebook_property_name):
    match str(codebook_property_name):
        case "DataRequestCategory":
            return (
                ";\r\n".join([g for g in observable_property.grouping_id_list])
                if observable_property.grouping_id_list
                else None
            )
        case "Varname":
            return varname
        case "Description":
            return observable_property.description if observable_property.description else observable_property.ui_label
        case "Type":
            if observable_property.categorical:
                return "categorical"
            return DATATYPE_TRANSLATION_DICT[observable_property.value_type]
        case "Unit":
            return None
        case "MissingsAllowed":
            return 0 if observable_property.default_required else 1
        case "MinValue":
            return None
        case "MaxValue":
            return None
        case "AllowedValues":
            if observable_property.categorical:
                return ";\r\n".join([vo.key + " = " + vo.value for vo in observable_property.value_options])
            else:
                return None
        case "DecimalsAfterComma":
            return None
        case "Conditional":
            return None
        case "Formula":
            return None
        case "Remarks":
            return None


def fill_excel_form_sheet(worksheet, style_dict, header_list=None, metadata_record_dict=None, autofit=True):
    for counter, header in enumerate(header_list):
        worksheet.write(0, counter, header, style_dict["header"])
    for counter, metadata_record_key in enumerate(metadata_record_dict.keys()):
        worksheet.write(counter + 1, 0, metadata_record_key)
        worksheet.write(counter + 1, 1, metadata_record_dict[metadata_record_key])
    if autofit:
        worksheet.autofit()


def fill_excel_worksheet_from_section(
    worksheet, section, observable_property_dict, style_dict, observed_values=None, data_list=None, autofit=True
):
    match str(section.section_type):
        case "data_form":
            row = 0
            for element in section.elements:
                match str(element.element_type):
                    case "spacer":
                        pass
                    case "text":
                        worksheet.write(
                            row,
                            0,
                            element.label,
                            style_dict[str(element.element_style)]
                            if str(element.element_style) in style_dict.keys()
                            else None,
                        )
                    case "data_field":
                        worksheet.write(row, 0, element.label)
                        # default value: worksheet.write(row, 1, observable_property.default_value)
                row += 1
        case "data_table":
            column_ids = [element.varname for element in section.elements]
            for c_nr, c_name in enumerate(column_ids):
                worksheet.write(0, c_nr, c_name, style_dict["header"])
            if data_list is not None and isinstance(data_list, list):
                for r_nr, record in enumerate(data_list):
                    for c_nr, element in enumerate(record):
                        worksheet.write(r_nr + 1, c_nr, element)
            if observed_values is not None and isinstance(observed_values, list):
                row_ids = list(set(observed_value.observable_entity for observed_value in observed_values))
                for r_nr, r_name in enumerate(row_ids):
                    for c_nr, c_name in enumerate(column_ids):
                        worksheet.write(
                            r_nr + 1,
                            c_nr,
                            [
                                observed_value.value_as_string
                                for observed_value in observed_values
                                if observed_value.observable_entity == r_name
                                and observed_value.observable_property == c_name
                            ][0],
                        )
        case "property_table":
            columns = [
                "DataRequestCategory",
                "Varname",
                "Description",
                "Type",
                "Unit",
                "MissingsAllowed",
                "MinValue",
                "MaxValue",
                "AllowedValues",
                "DecimalsAfterComma",
                "Conditional",
                "Formula",
                "Remarks",
            ]
            for c_nr, c_name in enumerate(columns):
                worksheet.write(0, c_nr, c_name, style_dict["bold"])
            row = 1
            for element in section.elements:
                index_name = element.observable_property
                if index_name.endswith("_lod") or index_name.endswith("_loq"):
                    index_name = index_name[:-4]
                if (
                    index_name not in observable_property_dict
                    and f"mass concentration of {index_name} in urine" in observable_property_dict
                ):
                    index_name = f"mass concentration of {index_name} in urine"
                op = observable_property_dict[index_name]

                for c_nr, c_name in enumerate(columns):
                    worksheet.write(row, c_nr, get_observable_property_property(element.varname, op, c_name))
                row += 1
    if autofit:
        worksheet.autofit()


def write_excel_datatemplate(
    layout, path, observable_property_dict=None, studyinfo_header_list=None, codebook_metadata_dict=None
):
    try:
        import xlsxwriter
    except ImportError:
        logging.error("Install the 'xlsxwriter' module in order to use the ExportXlsx Adapter.")
        raise

    def create_analyticalinfo_dataset(layout):
        dataset = []
        for section in layout.sections:
            matrix = ANALYTICALINFO_MATRIX_TRANSLATION.get(section.ui_label)
            if matrix:
                dataset.extend(
                    [
                        (element.varname, matrix)
                        for element in section.elements
                        if not (
                            element.varname in ANALYTICALINFO_EXCLUSION_LIST or element.varname[-4:] in ["_lod", "_loq"]
                        )
                    ]
                )
        return dataset

    workbook = xlsxwriter.Workbook(path)
    style_dict = {
        "header": workbook.add_format({"font_color": "white", "bg_color": "#4F80BD", "bold": True}),
        "warning": workbook.add_format({"font_color": "red"}),
        "bold": workbook.add_format({"bold": True}),
    }
    worksheet = workbook.add_worksheet("studyinfo")
    worksheet.autofit()
    fill_excel_form_sheet(
        worksheet, style_dict, header_list=studyinfo_header_list, metadata_record_dict=codebook_metadata_dict
    )
    for section in layout.sections:
        worksheet = workbook.add_worksheet(section.ui_label)
        data_list = create_analyticalinfo_dataset(layout) if section.ui_label == "analyticalinfo" else None
        fill_excel_worksheet_from_section(worksheet, section, observable_property_dict, style_dict, data_list=data_list)
    workbook.close()


class ExportXlsxAdapter(ExportInterface):
    """Adapter for exporting data, schema and/or templates as xlsx files."""

    def export_data_template(
        self,
        layout,
        destination: str,
        observable_property_dict: dict = None,
        studyinfo_header_list: list = None,
        codebook_metadata_dict: dict = None,
    ) -> bool:
        write_excel_datatemplate(
            layout,
            destination,
            observable_property_dict=observable_property_dict,
            studyinfo_header_list=studyinfo_header_list,
            codebook_metadata_dict=codebook_metadata_dict,
        )
        return True

    def export_data_dictionary(
        self,
        observation_design,
        layout,
        destination: str,
        observable_property_dict: dict = None,
        studyinfo_header_list: list = None,
        codebook_metadata_dict: dict = None,
    ) -> bool:
        raise NotImplementedError

    def export_data(
        self,
        observation_result,
        layout,
        destination: str,
        observable_property_dict: dict = None,
        studyinfo_header_list: list = None,
        codebook_metadata_dict: dict = None,
    ) -> bool:
        raise NotImplementedError
