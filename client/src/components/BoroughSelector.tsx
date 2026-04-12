interface Props {
  boroughs: string[];
  selected: string | null;
  onSelect: (borough: string) => void;
}

export function BoroughSelector({ boroughs, selected, onSelect }: Props) {
  return (
    <div className="borough-selector">
      <select
        value={selected ?? ""}
        onChange={(e) => {
          if (e.target.value) onSelect(e.target.value);
        }}
      >
        <option value="">Select a borough...</option>
        {boroughs.map((b) => (
          <option key={b} value={b}>
            {b}
          </option>
        ))}
      </select>
    </div>
  );
}
