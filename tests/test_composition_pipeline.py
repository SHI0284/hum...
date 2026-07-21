from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import numpy as np
import soundfile as sf
from PIL import Image

from core.analyzer import SoundAnalyzer
from core.gradient_selector import GradientSelector
from core.image_composer import ImageComposer


class CompositionPipelineTest(unittest.TestCase):
    def test_windows_ascii_layer_path_is_supported(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            expected = root / "layers" / "A" / "night" / "Ac1_N.png"
            expected.parent.mkdir(parents=True)
            Image.new("RGBA", (8, 8), (255, 255, 255, 255)).save(expected)

            composer = ImageComposer(graphics_dir=root, output_dir=root / "results")

            self.assertEqual(composer._find_layer("c", "1", "night"), expected)

    def test_high_bright_sound_selects_day_and_creates_square_png(self) -> None:
        sample_rate = 44_100
        time = np.arange(sample_rate * 2, dtype="float64") / sample_rate
        audio = 0.42 * np.sin(2 * np.pi * 4_800 * time)
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            audio_path = root / "bright.wav"
            sf.write(audio_path, audio, sample_rate)
            analysis = SoundAnalyzer().analyze(audio_path)
            output = ImageComposer(output_dir=root / "results").compose(
                analysis, audio_path
            )

            self.assertEqual(analysis.day_night, "day")
            self.assertEqual(len(analysis.components), 6)
            self.assertEqual(len(set(analysis.components)), len(analysis.components))
            self.assertTrue(1 <= analysis.gradient_index <= 210)
            self.assertTrue(output.exists())
            with Image.open(output) as image:
                self.assertEqual(image.size, (720, 720))

    def test_quiet_low_sound_selects_night(self) -> None:
        sample_rate = 44_100
        time = np.arange(sample_rate * 2, dtype="float64") / sample_rate
        audio = 0.05 * np.sin(2 * np.pi * 110 * time)
        with tempfile.TemporaryDirectory() as temp_dir:
            audio_path = Path(temp_dir) / "low.wav"
            sf.write(audio_path, audio, sample_rate)
            analysis = SoundAnalyzer().analyze(audio_path)

            self.assertEqual(analysis.day_night, "night")
            self.assertGreater(analysis.low_energy, analysis.high_energy)

    def test_loudness_controls_layer_count(self) -> None:
        analyzer = SoundAnalyzer()
        self.assertEqual(analyzer._component_count(0.10), 1)
        self.assertEqual(analyzer._component_count(0.20), 2)
        self.assertEqual(analyzer._component_count(0.40), 3)
        self.assertEqual(analyzer._component_count(0.62), 4)
        self.assertEqual(analyzer._component_count(0.78), 5)
        self.assertEqual(analyzer._component_count(0.90), 6)

    def test_gradient_profiles_are_driven_by_sound_features(self) -> None:
        selector = GradientSelector()
        cases = {
            "cool_bright": (.65, .88, .18, .22, .05, .75),
            "pastel": (.25, .48, .10, .12, .30, .25),
            "contrast": (.90, .55, .85, .82, .25, .35),
            "warm_dark": (.62, .15, .28, .30, .78, .03),
        }
        selected: dict[str, int] = {}
        for expected_profile, values in cases.items():
            loudness, brightness, roughness, variability, low, high = values
            result = selector.select(
                loudness=loudness,
                brightness=brightness,
                roughness=roughness,
                variability=variability,
                fingerprint=0,
                low_energy=low,
                high_energy=high,
            )
            self.assertEqual(result.profile, expected_profile)
            selected[expected_profile] = result.index
        self.assertEqual(len(set(selected.values())), len(cases))


if __name__ == "__main__":
    unittest.main()
