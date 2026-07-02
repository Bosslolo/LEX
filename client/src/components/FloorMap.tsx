import type { AccessPoint, Floor, PersonLocation } from "@shared/types";

const COLORS = ["#3b82f6", "#22c55e", "#f59e0b", "#ec4899", "#8b5cf6", "#14b8a6"];

interface Props {
  floor: Floor;
  accessPoints: AccessPoint[];
  people: PersonLocation[];
}

export function FloorMap({ floor, accessPoints, people }: Props) {
  const vb = `0 0 ${floor.width} ${floor.height}`;

  return (
    <svg className="floor-svg" viewBox={vb} role="img" aria-label={floor.label}>
      <rect x={0} y={0} width={floor.width} height={floor.height} className="floor-bg" />

      {floor.rooms.map((room) => (
        <g key={room.id}>
          <rect x={room.x} y={room.y} width={room.w} height={room.h} className="room" rx={1.5} />
          <text x={room.x + room.w / 2} y={room.y + room.h / 2} className="room-label">
            {room.label}
          </text>
        </g>
      ))}

      {accessPoints.map((ap) => (
        <g key={ap.id} transform={`translate(${ap.x}, ${ap.y})`}>
          <circle r={2.2} className="ap-dot" />
          <text y={-3.5} className="ap-label">
            {ap.label.replace(/^AP\s*/, "")}
          </text>
        </g>
      ))}

      {people.map((person, i) => {
        const color = COLORS[i % COLORS.length]!;
        return (
          <g key={person.personId} transform={`translate(${person.x}, ${person.y})`}>
            <circle r={4} fill={color} className="person-pin" />
            <circle r={6} fill="none" stroke={color} strokeWidth={0.6} className="person-ring" opacity={0.5} />
            <text y={-7} className="person-label" fill={color}>
              {person.displayName}
            </text>
            {person.devices.length > 1 && (
              <text y={9} className="device-count">
                {person.devices.length} Geräte
              </text>
            )}
          </g>
        );
      })}
    </svg>
  );
}
