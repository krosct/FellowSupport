import OptionCard from "./OptionCard.jsx";
import ProfileBadges from "./ProfileBadges.jsx";

/** Seletor de perfil: um cartão por cliente, com nível, estilo e canal em badges. */
export default function ProfilePicker({ profiles, enums, value, onChange }) {
  return (
    <div className="option-list" role="radiogroup" aria-label="Perfil do cliente">
      {profiles.map((profile) => (
        <OptionCard key={profile.id} name="profile" value={profile.id} checked={value === profile.id} onChange={onChange}>
          <strong>{profile.name}</strong>
          <ProfileBadges profile={profile} enums={enums} />
        </OptionCard>
      ))}
    </div>
  );
}
