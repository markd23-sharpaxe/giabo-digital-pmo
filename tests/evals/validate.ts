import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { FrameworkScenarioArraySchema, ScenarioArraySchema } from "./types/evalSchema.ts";

const here = dirname(fileURLToPath(import.meta.url));

const chaser = ScenarioArraySchema.parse(
  JSON.parse(readFileSync(join(here, "datasets", "chaserScenarios.json"), "utf8")),
);
console.log(`PASS: ${chaser.length} chaser scenarios validated against ScenarioArraySchema.`);

const framework = FrameworkScenarioArraySchema.parse(
  JSON.parse(readFileSync(join(here, "datasets", "giaboFrameworkScenarios.json"), "utf8")),
);
console.log(`PASS: ${framework.length} framework scenarios validated against FrameworkScenarioArraySchema.`);
for (const scenario of framework) {
  console.log(`  - ${scenario.roleIndex}/27 ${scenario.targetAgentRole} (${scenario.id})`);
}
