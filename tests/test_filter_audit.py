"""Filtering alternatives count unique reviews and preserve closure exclusions."""
import unittest
import pandas as pd
from scripts.compare_matching import compare_service_filters

class FilterAudit(unittest.TestCase):
    def test_scope_alternatives_and_explicit_closure(self):
        places = pd.DataFrame([
            {'place_id':'a','category':'Shop','all_categories':'Pharmacy'},
            {'place_id':'b','category':'Convenience store'},
            {'place_id':'c','category':'Clinic','permanently_closed':'TRUE'},
            {'place_id':'d','category':'Clinic','permanently_closed':'unknown'},
            {'place_id':'d','category':'Clinic','permanently_closed':'unknown'},
        ])
        reviews = pd.DataFrame({'place_id':['a','a','b','c','d']})
        crosswalk = pd.DataFrame({'source_place_id':['a','b','c','d'], 'place_id':['a','b','c','d']})
        counts = compare_service_filters(places,crosswalk,reviews)
        self.assertEqual([r['eligible_review_rows_before_deduplication'] for r in counts], [1,3,4])
        self.assertEqual([r['matched_places'] for r in counts], [1,2,3])
        self.assertTrue(counts[-1]['changes_service_scope'])
