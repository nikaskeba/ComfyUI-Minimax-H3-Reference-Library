import json
from pathlib import Path
import unittest


WORKFLOW = Path(__file__).resolve().parents[1] / "workflows" / "tool_MuScriptor Example.json"


class ExampleWorkflowSyncTests(unittest.TestCase):
    def test_shared_abc_audio_and_combined_output(self):
        workflow = json.loads(WORKFLOW.read_text(encoding="utf-8"))
        nodes = {node["id"]: node for node in workflow["nodes"]}
        links = {link[0]: link for link in workflow["links"]}
        self.assertEqual(len(links), len(workflow["links"]))
        for link in links.values():
            _, source, source_slot, target, target_slot, kind = link
            self.assertIn(link[0], nodes[source]["outputs"][source_slot]["links"])
            self.assertEqual(nodes[target]["inputs"][target_slot]["link"], link[0])
            self.assertEqual(nodes[source]["outputs"][source_slot]["type"], kind)
            self.assertEqual(nodes[target]["inputs"][target_slot]["type"], kind)

        shared = next(node for node in nodes.values() if node["type"] == "SkebaABCSharedTempo")
        score = next(node for node in nodes.values() if node["type"] == "SkebaABCToMidi")
        muscriptor = next(node for node in nodes.values() if node["type"] == "SkebaMuScriptorGrid")
        combine = next(node for node in nodes.values() if node["type"] == "SkebaCombineTranscriptionMIDIs")
        sheetsage = next(node for node in nodes.values() if node["type"] == "SkebaSheetSage2AudioToABC")
        audio = next(node for node in nodes.values() if node["type"] == "VHS_LoadAudioUpload")
        self.assertEqual(links[shared["inputs"][0]["link"]][1], sheetsage["id"])
        self.assertEqual(links[score["inputs"][0]["link"]][1], shared["id"])
        self.assertEqual(links[muscriptor["inputs"][0]["link"]][1], shared["id"])
        self.assertEqual(links[sheetsage["inputs"][1]["link"]][1], audio["id"])
        self.assertEqual(links[muscriptor["inputs"][1]["link"]][1], audio["id"])
        self.assertEqual(links[muscriptor["inputs"][2]["link"]][1:4], [sheetsage["id"], 2, muscriptor["id"]])
        self.assertEqual(muscriptor["widgets_values_named"]["tempo_override_bpm"], 0)
        self.assertEqual(links[combine["inputs"][0]["link"]][1], score["id"])
        self.assertEqual(links[combine["inputs"][1]["link"]][1], muscriptor["id"])
        self.assertTrue(any(link[1] == combine["id"] and nodes[link[3]]["type"] == "SkebaSaveMidi"
                            for link in links.values()))


if __name__ == "__main__":
    unittest.main()
