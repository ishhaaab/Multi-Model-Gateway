"""Unit tests for app.services.comfy.inject_lora (ComfyUI LoraLoader injection).

Stdlib unittest only — no pytest dependency. Tests are offline (no DB, no
network): inject_lora is a pure function over a workflow dict. If the module
can't be imported in this environment (missing settings/secret deps), the
whole suite skips cleanly.
"""
import copy
import unittest

try:
    from app.services.comfy import BASE_WORKFLOW, inject_lora, _find_node
except Exception as exc:  # noqa: BLE001 — env may lack required settings
    BASE_WORKFLOW = None
    inject_lora = None
    _find_node = None
    _IMPORT_ERROR = exc
else:
    _IMPORT_ERROR = None


class InjectLoraTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if inject_lora is None:
            raise unittest.SkipTest(
                f"app.services.comfy import failed in this env: {_IMPORT_ERROR}"
            )

    def test_inject_lora_rewires_base_workflow(self):
        """Injecting a LoRA adds a LoraLoader node and routes the sampler's
        model + every CLIPTextEncode's clip through it."""
        graph = inject_lora(copy.deepcopy(BASE_WORKFLOW), "lora_fake.safetensors")

        lora_ids = [
            node_id
            for node_id, node in graph.items()
            if node.get("class_type") == "LoraLoader"
        ]
        self.assertEqual(len(lora_ids), 1, "exactly one LoraLoader node expected")
        lora_id = lora_ids[0]

        # KSampler pulls its model from the LoRA node
        sampler_id, sampler = _find_node(graph, "KSampler")
        self.assertIsNotNone(sampler)
        self.assertEqual(sampler["inputs"]["model"], [lora_id, 0])

        # every CLIPTextEncode pulls its clip from the LoRA node's second output
        for node_id, node in graph.items():
            if node.get("class_type") == "CLIPTextEncode":
                self.assertEqual(node["inputs"]["clip"], [lora_id, 1])

    def test_existing_lora_loader_returns_graph_unchanged(self):
        """A workflow that already loads a LoRA is left untouched."""
        graph = copy.deepcopy(BASE_WORKFLOW)
        graph["99"] = {
            "class_type": "LoraLoader",
            "inputs": {"model": ["4", 0], "clip": ["4", 1],
                       "lora_name": "already.safetensors",
                       "strength_model": 1.0, "strength_clip": 1.0},
        }
        before = copy.deepcopy(graph)

        result = inject_lora(graph, "lora_fake.safetensors")

        self.assertIs(result, graph, "the same graph object should come back")
        self.assertEqual(result, before, "graph content must be unchanged")

    def test_missing_ksampler_returns_graph_unchanged(self):
        """No KSampler means nothing to anchor on — graph passes through."""
        graph = {"1": {"class_type": "CLIPTextEncode", "inputs": {"clip": ["2", 1]}}}
        before = copy.deepcopy(graph)

        result = inject_lora(graph, "lora_fake.safetensors")

        self.assertEqual(result, before)


if __name__ == "__main__":
    unittest.main()
