"""Model invariants on invented text; these are not independent accuracy results."""
import json
from pathlib import Path
import tempfile
import unittest

import numpy as np
import pandas as pd
from sklearn.dummy import DummyClassifier
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.naive_bayes import MultinomialNB
from sklearn.pipeline import FeatureUnion
from sklearn.metrics import f1_score

NOTEBOOK = Path(__file__).resolve().parents[1] / 'Access_Beyond_the_Map.ipynb'
ASPECTS = ['physical', 'sensory', 'language', 'financial', 'time']
STATES = ['no_mention', 'barrier_reported', 'positive_access', 'unclear_or_mixed']


class ModelInvariants(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cells = json.loads(NOTEBOOK.read_text())['cells']
        source = next(''.join(c['source']) for c in cells if 'class AspectModel:' in ''.join(c['source']))
        source = source[source.index('class AspectModel:'):source.index('models={"keywords":None}')]
        cls.ns = dict(globals(), SEED=42)
        exec(source, cls.ns)

    def frame(self):
        frame = pd.DataFrame({'review': ['steps blocked entrance', 'ramp helped entry', 'lovely friendly staff', 'entry sometimes blocked'] * 3})
        for aspect in ASPECTS:
            frame[aspect] = ['barrier_reported', 'positive_access', 'no_mention', 'unclear_or_mixed'] * 3
        return frame

    def test_distinct_estimators_and_aligned_finite_scores(self):
        for variant, estimator in [('word', LogisticRegression), ('nb', MultinomialNB), ('majority', DummyClassifier)]:
            with self.subTest(variant=variant):
                model = self.ns['AspectModel'](variant).fit(self.frame())
                self.assertIsInstance(model.models['physical'], estimator)
                probabilities = model.predict_proba(['unknown vocabulary', 'steps blocked entrance'])
                self.assertEqual(probabilities.shape, (2, 5, 4))
                self.assertTrue(np.isfinite(probabilities).all())
                self.assertTrue((probabilities >= 0).all())
                np.testing.assert_allclose(probabilities.sum(axis=2), 1)
                # Model classes are alphabetic; output columns must follow STATES instead.
                raw = model.models['physical'].predict_proba(model.vectorizer.transform(['steps blocked entrance']))[0]
                for k, state in enumerate(model.models['physical'].classes_):
                    self.assertAlmostEqual(probabilities[1, 0, STATES.index(state)], raw[k])
                self.assertNotIn('unknown', model.vectorizer.vocabulary_)

    def test_constant_training_state_and_unseen_classes(self):
        frame = self.frame()
        frame['physical'] = 'positive_access'
        model = self.ns['AspectModel']('nb').fit(frame)
        p = model.predict_proba(['steps blocked'])
        np.testing.assert_array_equal(p[0, 0], [0, 0, 1, 0])
        self.assertEqual(self.ns['decode'](p, [.5] * 5)[0, 0], 'positive_access')

    def test_missing_validation_positives_disable_barrier_flags(self):
        probabilities = np.full((3, 5, 4), .25)
        thresholds = self.ns['tune_thresholds'](probabilities, np.zeros((3, 5), dtype=int))
        self.assertEqual(thresholds, [1.01] * 5)
        self.assertFalse((self.ns['decode'](probabilities, thresholds) == 'barrier_reported').any())

class HumanLabelGate(unittest.TestCase):
    def test_incomplete_review_excluded_and_nonhuman_labels_ignored(self):
        cells = json.loads(NOTEBOOK.read_text())['cells']
        source = next(''.join(c['source']) for c in cells if 'def load_gold(' in ''.join(c['source']))
        source = source[source.index('def load_gold('):source.index('gold_dev=')]
        with tempfile.TemporaryDirectory() as directory:
            frame = pd.DataFrame({'record_id': ['a', 'b', 'c'], 'split': ['test'] * 3, 'review': ['steps blocked'] * 3})
            rows = []
            for record in ['a', 'b', 'c']:
                for aspect in ASPECTS:
                    if record == 'b' and aspect == 'time':
                        continue
                    rows.append(dict(record_id=record, aspect=aspect, state='no_mention', evidence='', annotator_id='reviewer1', provenance='machine' if record == 'c' else 'human', adjudicated=True))
            path = Path(directory)
            pd.DataFrame(rows).to_csv(path / 'labels.csv', index=False)
            ns = dict(globals(), MODE='real', DATA_DIR=path, df=frame)
            exec(source, ns)
            self.assertEqual(ns['load_gold'](['test']).record_id.tolist(), ['a'])
            self.assertTrue(ns['load_gold'](['train']).empty)
            rows[0].update(state='barrier_reported', evidence='invented quote')
            pd.DataFrame(rows).to_csv(path / 'labels.csv', index=False)
            with self.assertRaisesRegex(AssertionError, 'Evidence must be'):
                ns['load_gold'](['test'])


if __name__ == '__main__':
    unittest.main()
