import Image from "next/image";

interface OrionLogoProps {
  size?: number;
  className?: string;
}

/**
 * Orion AI logo — renders /icon.svg from public/.
 * Falls back to an inline SVG if the file is missing.
 */
export default function OrionLogo({ size = 36, className = "" }: OrionLogoProps) {
  return (
    <Image
      src="/icon.svg"
      alt="Orion AI"
      width={size}
      height={size}
      className={className}
      style={{ objectFit: "contain" }}
      priority
    />
  );
}
