import { HlhpProvider } from "@/lib/store";
import { AppFrame } from "@/components/shell/AppFrame";

export default function Home() {
  return (
    <HlhpProvider>
      <AppFrame />
    </HlhpProvider>
  );
}
