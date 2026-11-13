import type { AccessPoint, Floor, PersonLocation } from "@shared/types";

const COLORS = ["#5ec8e8", "#4ade80", "#fbbf24", "#fb7185", "#38bdf8", "#34d399"];

interface Props {
  floor: Floor;
  accessPoints: AccessPoint[];
  people: PersonLocation[];
}

export function FloorMap({ floor, accessPoints, people }: Props) {
  const vb = `0 0 ${floor.width} ${floor.height}`;

  return (
    <svg className="floor-svg" viewBox={vb} role="img" aria-label={floor.label}>
      <defs>
        <pattern id="grid" width="4" height="4" patternUnits="userSpaceOnUse">
          <path d="M 4 0 L 0 0 0 4" fill="none" stroke="rgba(125,168,196,0.05)" strokeWidth="0.25" />
        </pattern>
        <filter id="softGlow" x="-50%" y="-50%" width="200%" height="200%">
          <feGaussianBlur stdDeviation="0.8" result="blur" />
          <feMerge>
            <feMergeNode in="blur" />
            <feMergeNode in="SourceGraphic" />
          </feMerge>
        </filter>
      </defs>

      <rect x={0} y={0} width={floor.width} height={floor.height} className="floor-bg" rx={2} />
      <rect x={0} y={0} width={floor.width} height={floor.height} fill="url(#grid)" rx={2} />

      {floor.rooms.map((room) => (
        <g key={room.id}>
          <rect x={room.x} y={room.y} width={room.w} height={room.h} className="room" rx={1.8} />
          <text x={room.x + room.w / 2} y={room.y + room.h / 2} className="room-label">
            {room.label}
          </text>
        </g>
      ))}

      {accessPoints.map((ap) => (
        <g key={ap.id} transform={`translate(${ap.x}, ${ap.y})`}>
          <title>{ap.label}</title>
          <circle r={3.6} className="ap-ring" />
          <circle r={1.55} className="ap-dot" />
        </g>
      ))}

      {people.map((person, i) => {
        const color = COLORS[i % COLORS.length]!;
        return (
          <g key={person.personId} transform={`translate(${person.x}, ${person.y})`} filter="url(#softGlow)">
            <circle r={6.5} fill="none" stroke={color} className="person-ring" />
            <circle r={3.6} fill={color} className="person-pin" />
            <text y={-7.2} className="person-label" fill={color}>
              {person.displayName}
            </text>
            {person.devices.length > 1 && (
              <text y={8.4} className="device-count">
                {person.devices.length} Geräte
              </text>
            )}
          </g>
        );
      })}
    </svg>
  );
}
