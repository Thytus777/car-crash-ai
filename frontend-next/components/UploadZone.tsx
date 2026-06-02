"use client";

import { useRef, useState } from "react";
import clsx from "clsx";

interface Props {
  onFiles: (files: File[]) => void;
  disabled?: boolean;
}

export default function UploadZone({ onFiles, disabled }: Props) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [dragging, setDragging] = useState(false);

  function handleFiles(fileList: FileList | null) {
    if (!fileList) return;
    const accepted = Array.from(fileList).filter((f) =>
      ["image/jpeg", "image/png", "image/heic", "image/heif"].includes(f.type)
    );
    if (accepted.length) onFiles(accepted);
  }

  return (
    <div
      onClick={() => !disabled && inputRef.current?.click()}
      onDragOver={(e) => { e.preventDefault(); setDragging(true); }}
      onDragLeave={() => setDragging(false)}
      onDrop={(e) => { e.preventDefault(); setDragging(false); handleFiles(e.dataTransfer.files); }}
      className={clsx(
        "border-2 border-dashed rounded-xl p-10 text-center cursor-pointer transition-colors",
        dragging ? "border-brand bg-blue-50" : "border-gray-300 hover:border-brand hover:bg-gray-50",
        disabled && "opacity-50 cursor-not-allowed"
      )}
    >
      <input
        ref={inputRef}
        type="file"
        multiple
        accept="image/jpeg,image/png,image/heic,image/heif"
        className="hidden"
        onChange={(e) => handleFiles(e.target.files)}
        disabled={disabled}
      />
      <div className="text-4xl mb-3">📷</div>
      <p className="font-semibold text-gray-700">Drop photos here or click to browse</p>
      <p className="text-sm text-gray-400 mt-1">JPEG, PNG, HEIC · up to 20 MB each · max 10 photos</p>
      <p className="text-xs text-gray-400 mt-2">
        For best results: front, rear, driver side, passenger side
      </p>
    </div>
  );
}
