"use client";

import { useCallback, useState } from "react";
import { useDropzone } from "react-dropzone";
import { Card } from "@/components/ui/card";
import { FileText, Upload, X, CheckCircle2, Loader2 } from "lucide-react";
import { cn } from "@/lib/utils";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

interface UploadedFile {
  file: File;
  content: string;
}

interface FileUploadProps {
  type: "resume" | "jd";
  label: string;
  onFileUploaded: (content: string) => void;
}

export function FileUpload({ type, label, onFileUploaded }: FileUploadProps) {
  const [uploadedFile, setUploadedFile] = useState<UploadedFile | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isProcessing, setIsProcessing] = useState(false);

  const onDrop = useCallback(
    async (acceptedFiles: File[]) => {
      const file = acceptedFiles[0];
      if (!file) return;

      setError(null);
      setIsProcessing(true);

      try {
        // Send file to backend for text extraction
        const formData = new FormData();
        formData.append("file", file);

        const response = await fetch(`${API_URL}/api/extract-text`, {
          method: "POST",
          body: formData,
        });

        if (!response.ok) {
          throw new Error("Failed to process file");
        }

        const data = await response.json();

        if (!data.success) {
          setError(data.error || "Failed to extract text from file");
          setIsProcessing(false);
          return;
        }

        setUploadedFile({ file, content: data.text });
        onFileUploaded(data.text);
      } catch (err) {
        console.error("Upload error:", err);
        setError("Failed to process file. Please make sure the backend is running.");
      } finally {
        setIsProcessing(false);
      }
    },
    [onFileUploaded]
  );

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    accept: {
      "text/plain": [".txt"],
      "application/pdf": [".pdf"],
    },
    maxFiles: 1,
    disabled: isProcessing,
  });

  const removeFile = () => {
    setUploadedFile(null);
    onFileUploaded("");
  };

  const gradients = {
    resume: "from-emerald-500 to-teal-600",
    jd: "from-blue-500 to-indigo-600",
  };

  return (
    <Card
      {...getRootProps()}
      className={cn(
        "relative p-4 cursor-pointer transition-all duration-300 border-2 border-dashed",
        isDragActive
          ? "border-primary bg-primary/5 scale-[1.02]"
          : "border-muted-foreground/20 hover:border-primary/50 hover:bg-muted/50",
        uploadedFile && "border-solid border-green-500/50 bg-green-500/5",
        isProcessing && "opacity-70 cursor-wait"
      )}
    >
      <input {...getInputProps()} />

      {isProcessing ? (
        <div className="flex items-center gap-3">
          <div
            className={cn(
              "w-10 h-10 rounded-lg flex items-center justify-center bg-gradient-to-br",
              gradients[type]
            )}
          >
            <Loader2 className="w-5 h-5 text-white animate-spin" />
          </div>
          <div className="flex-1 min-w-0">
            <p className="text-sm font-medium">Processing...</p>
            <p className="text-xs text-muted-foreground">
              Extracting text from PDF
            </p>
          </div>
        </div>
      ) : uploadedFile ? (
        <div className="flex items-center gap-3">
          <div
            className={cn(
              "w-10 h-10 rounded-lg flex items-center justify-center bg-gradient-to-br",
              gradients[type]
            )}
          >
            <CheckCircle2 className="w-5 h-5 text-white" />
          </div>
          <div className="flex-1 min-w-0">
            <p className="text-sm font-medium truncate">
              {uploadedFile.file.name}
            </p>
            <p className="text-xs text-muted-foreground">
              {(uploadedFile.file.size / 1024).toFixed(1)} KB • {uploadedFile.content.length} chars extracted
            </p>
          </div>
          <button
            onClick={(e) => {
              e.stopPropagation();
              removeFile();
            }}
            className="p-1.5 rounded-full hover:bg-destructive/10 transition-colors"
          >
            <X className="w-4 h-4 text-muted-foreground hover:text-destructive" />
          </button>
        </div>
      ) : (
        <div className="flex flex-col items-center gap-2 py-2">
          <div
            className={cn(
              "w-12 h-12 rounded-xl flex items-center justify-center bg-gradient-to-br transition-transform",
              gradients[type],
              isDragActive && "scale-110"
            )}
          >
            {isDragActive ? (
              <Upload className="w-6 h-6 text-white animate-bounce" />
            ) : (
              <FileText className="w-6 h-6 text-white" />
            )}
          </div>
          <div className="text-center">
            <p className="text-sm font-medium">{label}</p>
            <p className="text-xs text-muted-foreground">
              Drag & drop or click to upload
            </p>
          </div>
        </div>
      )}

      {error && (
        <p className="text-xs text-destructive mt-2 text-center">{error}</p>
      )}
    </Card>
  );
}
