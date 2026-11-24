"use client";

import { useEffect, useId, useMemo, useState } from "react";

const ACCEPTED = ["image/jpeg", "image/png", "image/heic", "image/heif"];
const MAX_FILES = 10;

interface Props {
  files: File[];
  onFiles: (files: File[]) => void;
  disabled?: boolean;
}

/** Browsers can't draw HEIC, so those photos show as a labelled blank. */
function canPreview(file: File): boolean {
  return file.type === "image/jpeg" || file.type === "image/png";
}

export default function UploadZone({ files, onFiles, disabled }: Props) {
  const inputId = useId();
  const [dragging, setDragging] = useState(false);
  const previews = useMemo(
    () => files.map((f) => (canPreview(f) ? URL.createObjectURL(f) : null)),
    [files],
  );
  useEffect(() => () => previews.forEach((url) => url && URL.revokeObjectURL(url)), [previews]);

  function accept(list: FileList | null) {
    if (!list || disabled) return;
    const picked = Array.from(list).filter((f) => ACCEPTED.includes(f.type)).slice(0, MAX_FILES);
    if (picked.length) onFiles(picked);
  }

  return (
    <div>
      <label
        htmlFor={inputId}
        className="dropzone"
        data-dragging={dragging}
        aria-disabled={disabled}
        onDragOver={(e) => {
          e.preventDefault();
          if (!disabled) setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={(e) => {
          e.preventDefault();
          setDragging(false);
          accept(e.dataTransfer.files);
        }}
      >
        <p className="dropzone__main">
          {files.length ? "Choose different photos" : "Choose photos or drop them here"}
        </p>
        <p className="dropzone__sub">
          JPEG, PNG or HEIC, up to 10 photos of 20 MB each. Front, rear and both sides work best.
        </p>
      </label>
      <input
        id={inputId}
        className="visually-hidden"
        type="file"
        multiple
        accept={ACCEPTED.join(",")}
        disabled={disabled}
        onChange={(e) => accept(e.target.files)}
      />

      {files.length > 0 && (
        <ul className="photos" aria-label={`${files.length} photo${files.length === 1 ? "" : "s"} selected`}>
          {files.map((file, i) => (
            <li className="photo" key={`${file.name}-${i}`}>
              <div className="photo__frame">
                {previews[i] && <img src={previews[i]} alt="" />}
              </div>
              <span className="photo__name">{file.name}</span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
