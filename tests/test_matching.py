import unittest
import pandas as pd
from access_app.matching import match_review_places, enrich_osm


class MatchingTests(unittest.TestCase):
    def setUp(self):
        self.p = pd.DataFrame([
            dict(place_id='a', name='Clinic North', address='100 Main Street Town NY 10001', cid='123', lat=40, lon=-74),
            dict(place_id='b', name='Clinic South', address='200 Main Street Town NY 10001', cid='456', lat=40.01, lon=-74)])

    def match(self, rows):
        return match_review_places(self.p, pd.DataFrame(rows))

    def test_exact_cid_fid_and_name_address(self):
        result, audit = self.match([
            dict(place_id='a'), dict(place_id='old', fid_location='0xabc:0x1c8'),
            dict(place_id='new', place_name='CLINIC NORTH', address='100 Main Street, Town NY 10001'),
            dict(place_id='cid', url='https://maps.google.com/?cid=123')])
        self.assertEqual(result.place_id.tolist(), ['a', 'b', 'a', 'a'])
        self.assertEqual(audit['alternatives'][-1]['coverage'], 1)
        self.assertEqual(audit['alternatives'][0]['coverage'], .25)

    def test_no_name_only_or_wrong_branch(self):
        result, _ = self.match([dict(place_id='x', place_name='Clinic North'),
                               dict(place_id='y', place_name='Clinic North', address='999 Main Street Town NY 10001')])
        self.assertTrue(result.place_id.isna().all())

    def test_conflicting_keys_and_nonunique_key_rejected(self):
        result, _ = self.match([dict(place_id='x', cid='456', place_name='Clinic North', address='100 Main Street Town NY 10001')])
        self.assertEqual(result.iloc[0].match_status, 'ambiguous_or_conflicting')
        self.p.loc[1, 'cid'] = '123'
        result, _ = self.match([dict(place_id='x', cid='123')])
        self.assertTrue(result.place_id.isna().all())

    def test_entity_conflict_review_rows_and_exact_precedence(self):
        result, audit = self.match([dict(place_id='x', cid='123'), dict(place_id='x', cid='456'),
                                   dict(place_id='a', cid='456'), dict(place_id=None)])
        self.assertEqual(len(result), 2)
        self.assertEqual(result.iloc[0].match_status, 'ambiguous_or_conflicting')
        self.assertEqual(result.iloc[1].place_id, 'a')
        self.assertEqual(audit['missing_source_id_rows'], 1)

    def test_conflicting_source_metadata_even_if_second_target_absent(self):
        result, _ = self.match([dict(place_id='x', cid='123'), dict(place_id='x', cid='999')])
        self.assertEqual(result.iloc[0].match_status, 'ambiguous_or_conflicting')

    def test_empty_and_float_cid_does_not_round_identifier(self):
        result, audit = self.match([dict(place_id='x', cid='123.0'), dict(place_id='y', url='https://evil.com/?cid=123')])
        self.assertTrue(result.place_id.isna().all())
        result, audit = match_review_places(self.p, pd.DataFrame(columns=['place_id']))
        self.assertEqual(audit['alternatives'][-1]['coverage'], 0)

    def osm(self, features):
        return enrich_osm(self.p, {'features': features}, source_url='https://www.openstreetmap.org', retrieved_at='2026-11-15')

    def feature(self, fid='node/1', lon=-74, name='Clinic North', tags=None):
        return dict(id=fid, geometry={'type':'Point', 'coordinates':[lon, 40]}, properties={'name': name, **(tags or {})})

    def test_osm_strict_distance_unknown_and_provenance(self):
        out = self.osm([self.feature(tags={'opening_hours':'Mo-Fr 09:00-17:00'})])
        self.assertEqual(len(out), 1)
        self.assertIsNone(out.iloc[0].wheelchair)
        self.assertIn('ODbL', out.iloc[0].attribution)
        self.assertTrue(self.osm([self.feature(lon=-75)]).empty)

    def test_osm_ambiguity_and_reused_feature_rejected(self):
        self.assertTrue(self.osm([self.feature(), self.feature(fid='node/2')]).empty)
        self.p.loc[1, ['name', 'lat']] = ['Clinic North', 40]
        self.assertTrue(self.osm([self.feature()]).empty)

    def test_osm_requires_provenance(self):
        with self.assertRaises(ValueError):
            enrich_osm(self.p, {}, source_url='', retrieved_at='')


if __name__ == '__main__':
    unittest.main()
