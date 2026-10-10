import pytest
import synth

from ocr_core.classifier import ScreenClassifier


@pytest.mark.parametrize("screen", ["waiting", "camera", "ingame", "results"])
def test_classifies_painted_screen(config, screen):
    img = synth.blank(config.layout)
    synth.paint_probes(img, config.layout, screen)
    clf = ScreenClassifier(config.layout["classifier"], config.base_dir)
    assert clf.classify(img)[0] == screen


def test_blank_is_unknown(config):
    clf = ScreenClassifier(config.layout["classifier"], config.base_dir)
    assert clf.classify(synth.blank(config.layout))[0] == "unknown"
