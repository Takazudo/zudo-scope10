import { defineConfig } from "zfb/config";
import { zudoDoc } from "@takazudo/zudo-doc/config";
export default defineConfig(zudoDoc({
  siteName: "zudo-scope10 / P0",
  llmsTxt: true,
  imageEnlarge: true,
  assetViewer: true,
  docHistory: false,
  headerNav: [
    { label: "Start", path: "/docs/getting-started", categoryMatch: "getting-started" },
    { label: "Design", path: "/docs/architecture", categoryMatch: "architecture" },
    { label: "Build", path: "/docs/how-to", categoryMatch: "how-to" },
    { label: "Components", path: "/docs/components", categoryMatch: "components" }
  ]
}));
