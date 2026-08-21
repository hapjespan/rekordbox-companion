import { EnrichmentPanel } from "../features/enrichment/EnrichmentPanel";

// US6 (enrich the collection's genres). Like the Collection view, the
// delivered prototype has no design for it, so it follows the shell's header
// pattern and then mounts the panel unchanged.
export function EnrichmentView() {
  return (
    <div className="flex flex-col gap-24">
      <div className="flex flex-col gap-8">
        <h1 className="text-heading leading-heading font-bold text-pure-white">Genre-verrijking</h1>
        <p className="text-body text-mist">
          Vul de genres aan van nummers die er in Rekordbox geen hebben, automatisch of met de hand.
        </p>
      </div>

      <EnrichmentPanel />
    </div>
  );
}
