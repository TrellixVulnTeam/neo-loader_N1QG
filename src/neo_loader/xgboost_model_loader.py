import logging
import pickle
import copyreg
import builtins
import treelite
import xgboost.core

from typing import Dict, List
from pathlib import Path
from .abstract_model_loader import AbstractModelLoader
from ._base import GraphIR

logger = logging.getLogger(__name__)

# To un-pickle (somewhat) safely, explicitly whitelist globals
# This is not fool-proof, but inside a container, it might be enough
SAFE_BUILTINS = {'object', 'bytearray'}
SAFE_COPYREG = {'_reconstructor'}


class RestrictedUnpickler(pickle.Unpickler):
    def find_class(self, module, name):
        if module in ['builtins', '__builtin__'] and name in SAFE_BUILTINS:
            return getattr(builtins, name)
        if module in ['copy_reg', 'copyreg'] and name in SAFE_COPYREG:
            return getattr(copyreg, name)
        if module == 'xgboost.core':
            return getattr(xgboost.core, name)
        raise pickle.UnpicklingError("Global '{}.{}' is forbidden".format(module, name))


class XGBoostModelLoader(AbstractModelLoader):

    def __init__(self, model_artifacts: List[str], data_shape: Dict[str, List[int]]) -> None:
        super(XGBoostModelLoader, self).__init__(model_artifacts, data_shape)
        self.__model_objects = None

    @property
    def ir_format(self) -> GraphIR:
        return GraphIR.treelite

    @property
    def metadata(self) -> Dict[str, Dict]:
        return {}

    @property
    def model_objects(self) -> treelite.Model:
        return self.__model_objects

    @property
    def aux_files(self) -> List[Path]:
        return []

    def __get_model_file_from_model_artifacts(self) -> Path:
        # For XGBoost, file extension doesn't matter, since we'll require that exactly one
        # file be given.
        if len(self.model_artifacts) > 1:
            raise RuntimeError('InputConfiguration: Invalid XGBoost model: only one XGBoost model file is allowed. '
                               'Please make sure the framework you select is correct.')
        return self.model_artifacts[0]

    def load_model(self) -> None:
        model_file = self.__get_model_file_from_model_artifacts()

        try:
            try:
                with open(model_file, "rb") as file:
                    bst = RestrictedUnpickler(file).load()
            except Exception as e:
                logger.info("Un-pickling failed; now try loading it as a regular XGBoost model: {}".format(e))
                self.__model_objects = treelite.Model.load(model_file.as_posix(), 'xgboost')
            else:
                self.__model_objects = treelite.Model.from_xgboost(bst)
            self.update_missing_metadata()
        except Exception as e:
            logger.exception("Failed to convert xgboost model. %s" % repr(e))
            msg = "InputConfiguration: Treelite failed to convert XGBoost model. Please make sure the framework you select is correct. {}".format(e)
            raise RuntimeError(msg)
