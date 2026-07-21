import { cn } from "@/lib/utils";
import React from "react";

type PanelCropFrameProps = {
  crop: [number, number, number, number];
  className?: string;
  children: React.ReactNode;
};

export default function PanelCropFrame({
  crop,
  className,
  children,
}: PanelCropFrameProps) {
  const [left, top, right, bottom] = crop;
  const width = right - left;
  const height = bottom - top;

  return (
    <div className={cn("relative size-full overflow-hidden", className)}>
      <div
        className="absolute"
        style={{
          left: `${(-left / width) * 100}%`,
          top: `${(-top / height) * 100}%`,
          width: `${100 / width}%`,
          height: `${100 / height}%`,
        }}
      >
        {children}
      </div>
    </div>
  );
}
