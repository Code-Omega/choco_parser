"""
Instantiation of the chord converters for each of the dataset to convert.
"""
import argparse
import logging
import os
import sys
from json import decoder
from typing import List

import jams
import pandas as pd

sys.path.append(os.path.dirname(os.getcwd()))
parsers_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'parsers'))
sys.path.append(parsers_path)
lark_converters_path = os.path.abspath(os.path.join(os.path.dirname(__file__), 'lark-converters'))
sys.path.append(lark_converters_path)

from constants import CHORD_NAMESPACES
from chord_converter import ChordConverter
from converter_utils import create_dir, update_chord_list

logging.basicConfig()
logging.root.setLevel(logging.NOTSET)
logger = logging.getLogger('choco.converters.converter_instances')

basedir = os.path.dirname(__file__)


def parse_jams(jams_path: str, output_path: str, filename: str, replace: bool = False,
               handle_error: bool = True) -> List:
    """
    Parser for JAMS files that replace the chord annotations with the converted ones.
    Parameters
    ----------
    jams_path : str
        The path of the JAMS file to be converted.
    output_path : str
        The path in which the converted JAMS will be saved.
    filename : str
        The name of the JAMS file parsed, used for saving the file with the same name
        as the original.
    replace : bool (default=False)
        Indicated whether to replace the annotation or to preserve the original ones
        and hence duplicate the annotation section of the original file.
    handle_error : bool
        Boolean parameter to set whether to stop the program if a conversion error is met
        (False) or to continue and skip the error (True).

    Returns
    -------
    chord_metadata : List[List]
        A list of list containing metadata about the chords converted, organised as
        follows: [original_chord, converted_chord, type(key, chord), occurrences]
    """
    chord_metadata = []
    try:
        original_jams = jams.load(jams_path, strict=False)
    except decoder.JSONDecodeError as de:
        logger.error(f'Unable to open file {filename}, due to error {de}')
        return []
    original_annotations = original_jams.annotations
    jam = jams.JAMS()
    jam.file_metadata = original_jams.file_metadata
    jam.sandbox = original_jams.sandbox

    all_annotations = []

    for annotation in original_annotations:
        dataset_name = annotation.namespace
        converter = ChordConverter(dataset_namespace=dataset_name, handle_error=handle_error)
        # make an exception for the jazz-corpus, for which we cannot convert the chord_roman, so far
        if dataset_name in (CHORD_NAMESPACES if dataset_name != 'chord_jparser_harte' else ['chord_harte']):
            converted_annotation = jams.Annotation(namespace='chord_harte')
            for observation in annotation:
                converted_value = converter.convert_chords(observation.value)
                logger.info(f'Converting chord: {observation.value} --> {converted_value}')
                converted_annotation.append(time=observation.time,
                                            duration=observation.duration,
                                            value=converted_value,
                                            confidence=observation.confidence)
                chord_metadata = update_chord_list(chord_metadata,
                                                   [observation.value,
                                                    converted_value,
                                                    'chord',
                                                    annotation.namespace,
                                                    'chord_harte',
                                                    1])
            all_annotations.append(converted_annotation)
        elif annotation.namespace == 'key_mode':
            converted_annotation = jams.Annotation(namespace='key_mode')
            for key_observation in annotation:
                try:
                    converted_key = converter.convert_keys(key_observation.value)
                    converted_annotation.append(time=key_observation.time,
                                                duration=key_observation.duration,
                                                value=converted_key,
                                                confidence=key_observation.confidence)
                    chord_metadata = update_chord_list(chord_metadata, [key_observation.value,
                                                                        converted_key,
                                                                        'key',
                                                                        annotation.namespace,
                                                                        'key_mode',
                                                                        1])
                except ValueError:
                    logger.error('Impossible to convert key information.')
            all_annotations.append(converted_annotation)

    if replace is False:
        for oa in original_annotations:
            if oa.namespace != 'key_mode':
                jam.annotations.append(oa)
    # append converted annotations
    for a in all_annotations:
        jam.annotations.append(a)

    try:  # attempt saving the JAMS annotation file to disk
        jam.save(os.path.join(output_path, filename), strict=False)
    except jams.exceptions.SchemaError as jes:  # dumping error, logging for now
        logging.error(f'Could not save: {jams_path} because error occurred: {jes}')

    return chord_metadata


def parse_jams_dataset(jams_path: str, output_path: str, replace: bool = False,
                       handle_error: bool = True) -> None:
    """
    Parser for JAMS files datasets that replace the chord annotations with the converted ones.
    Parameters
    ----------
    jams_path : str
        The path of the JAMS dataset to be converted.
    output_path : str
        The path in which the converted JAMS will be saved.
    replace : bool (default=False)
        Indicated whether to replace the annotation or to preserve the original ones
        and hence duplicate the annotation section of the original file.
    handle_error : bool
        Boolean parameter to set whether to stop the program if a conversion error is met
        (False) or to continue and skip the error (True).
    """
    converted_jams_dir = create_dir(os.path.join(output_path, "jams-converted"))
    metadata = []
    jams_files = os.listdir(jams_path)
    for file in jams_files:
        logger.info(f'\nConverting observation for file: {file}\n')
        if os.path.isfile(os.path.join(jams_path, file)):
            file_metadata = parse_jams(os.path.join(jams_path, file), converted_jams_dir, file,
                                       replace, handle_error)
            metadata = [update_chord_list(metadata, x) for x in file_metadata][0] if len(
                [update_chord_list(metadata, x) for x in file_metadata]) > 0 else metadata

    metadata_df = pd.DataFrame(metadata,
                               columns=['original_chord',
                                        'converted_chord',
                                        'annotation_type',
                                        'original_namespace',
                                        'converted_namespace',
                                        'occurrences'])
    metadata_df.sort_values(by=['occurrences', 'annotation_type'], inplace=True, ascending=False)
    logger.info(f'\nSaving conversion metadata file: {os.path.join(output_path, "conversion_meta.csv")}\n')
    metadata_df.to_csv(os.path.join(output_path, "conversion_meta.csv"), index=False)


def main():
    """
    Main function to read the arguments and call the conversion scripts.
    """
    parser = argparse.ArgumentParser(
        description='Converter scripts for ChoCo partitions.')

    parser.add_argument('input_dir', type=str,
                        help='Directory where original JAMS data is read.')
    parser.add_argument('out_dir', type=str,
                        help='Directory where converted JAMS will be saved.')
    # parser.add_argument('dataset_name', type=str, choices=ANNOTATION_SUPPORTED.keys(),
    #                     help='Name of the dataset to convert.')
    parser.add_argument('replace', type=bool,
                        help='Whether to replace the annotations with the conversion or not.')
    parser.add_argument('handle_error', type=bool,
                        help='Whether to raise an error if a chord is not converted or replace the chord with "N".',
                        default=True)

    args = parser.parse_args()

    parse_jams_dataset(args.input_dir,
                       args.out_dir,
                       # args.dataset_name,
                       args.replace,
                       args.handle_error)


if __name__ == '__main__':
    main()
