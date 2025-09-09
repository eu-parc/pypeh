import pytest
import yaml

from peh_model import peh
from pypeh.core.models.validation_dto import ValidationConfig

from tests.test_utils.dirutils import get_absolute_path


@pytest.mark.core
class TestBasicValidationConfig:
    def test_config(self):
        source = get_absolute_path("./input/observations.yaml")
        with open(source, "r") as f:
            obs = yaml.safe_load(f)
        observation_list = [peh.Observation(**observation) for observation in obs["observations"]]

        source = get_absolute_path("./input/observable_properties.yaml")
        with open(source, "r") as f:
            obs_prop_data = yaml.safe_load(f)
        observable_properties = [
            peh.ObservableProperty(**observable_property)
            for observable_property in obs_prop_data["observable_properties"]
        ]

        observable_property_dict = {op["id"]: op for op in observable_properties}
        observation_design_list = [getattr(observation, "observation_design", None) for observation in observation_list]
        if len([od for od in observation_design_list if od is not None]) == 0:
            raise AttributeError

        # code below is copied from validationservice: IMPROVE
        found = False
        for oep_set_name, validation_config in ValidationConfig.from_observation_list(
            observation_list,
            observable_property_dict,
        ):
            assert isinstance(oep_set_name, str)
            for column_dict in validation_config.columns:
                if column_dict.unique_name == "peh:adults_u_sg":
                    found = True

        assert found
