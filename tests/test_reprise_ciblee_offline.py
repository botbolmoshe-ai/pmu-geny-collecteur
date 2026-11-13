import unittest
from unittest.mock import MagicMock,patch
from pmu_geny.collecte_geny_v4 import lire_classement,parse_career
from pmu_geny.controle_historique import classifier
from scripts.collecter_un_cheval import cliquer_nom,attendre_partant

class RepriseTests(unittest.TestCase):
    def test_name_control_is_clicked_instead_of_empty_cell_center(self):
        cell=MagicMock();name=cell.get_by_text.return_value;name.count.return_value=1
        cliquer_nom(cell,'Illinois')
        cell.get_by_text.assert_called_once_with('Illinois',exact=True)
        name.click.assert_called_once_with(timeout=8000)
        cell.click.assert_not_called()

    def test_ambiguous_click_is_rejected(self):
        cell=MagicMock();cell.get_by_text.return_value.count.return_value=2
        with self.assertRaises(ValueError):cliquer_nom(cell,'Illinois')
        cell.get_by_text.return_value.click.assert_not_called()

    def test_late_rendering_of_participant_is_waited_for_without_new_navigation(self):
        page=MagicMock()
        row={'index':13,'cells':['13','','Illinois','H8']}
        with patch('scripts.collecter_un_cheval.get_rows',side_effect=[[],[row]]):
            matched=attendre_partant(page,{'nom':'ILLINOIS','numero':13})
        self.assertEqual(matched[0]['nom'],'Illinois')
        page.goto.assert_not_called()
        page.wait_for_timeout.assert_called_once_with(500)

    def test_dpg_source_status_is_preserved_without_invented_rank(self):
        self.assertEqual(lire_classement(['J. Raffestin','Dpg']),'Dpg')
        line='15/08/25 | Vittel | Attelé | 2 700 | D | - | Herbe | Crse H | 12 500 € | J. Raffestin | Dpg'
        result=parse_career('CARRIÈRE\nsur 1 courses',[line])
        self.assertEqual(result['performances'][0]['classement'],'Dpg')
        self.assertEqual(classifier(result),('COMPLET',[]))

if __name__=='__main__':unittest.main()
