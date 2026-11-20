import Badge from "./Badge.jsx";
import { labelOf } from "../lib/labels.js";

/** Nível técnico, estilo de comunicação e canal de um perfil, como badges. Rótulos vêm de /api/meta. */
export default function ProfileBadges({ profile, enums }) {
  return (
    <div className="badges">
      <Badge kind="level">{labelOf(enums.tech_level, profile.tech_level)}</Badge>
      <Badge kind="style">{labelOf(enums.comm_style, profile.comm_style)}</Badge>
      <Badge kind="channel">{labelOf(enums.channel, profile.channel)}</Badge>
    </div>
  );
}
