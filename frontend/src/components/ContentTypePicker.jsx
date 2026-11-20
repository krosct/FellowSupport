import SelectField from "./SelectField.jsx";

/**
 * Seletor do tipo de conteúdo. Os rótulos vêm de /api/meta: os quatro tipos e a opção "Todos" (`allOption`).
 */
export default function ContentTypePicker({ types, allOption, value, onChange }) {
  return <SelectField label="Conteúdo" value={value} onChange={onChange} options={[...types, allOption]} />;
}
