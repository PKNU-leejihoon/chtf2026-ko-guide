// 사용법: ocr_boxes 이미지... → 이미지별 JSON 한 줄 {"f":경로,"w":..,"h":..,"lines":[{"t":문자열,"c":신뢰도,"x","y","w","h"}]} (좌상단 기준 픽셀)
import Foundation
import Vision
import AppKit
for path in CommandLine.arguments.dropFirst() {
  autoreleasepool {
    guard let img = NSImage(contentsOfFile: path), let cg = img.cgImage(forProposedRect: nil, context: nil, hints: nil) else { return }
    let W = CGFloat(cg.width), H = CGFloat(cg.height)
    var lines: [[String: Any]] = []
    // 긴 이미지는 조각으로 나눠 인식 정확도를 유지한다
    let step: CGFloat = 1300, overlap: CGFloat = 120
    var top: CGFloat = 0
    while top < H {
      let h = min(step + overlap, H - top)
      guard let crop = cg.cropping(to: CGRect(x: 0, y: top, width: W, height: h)) else { break }
      let req = VNRecognizeTextRequest()
      req.recognitionLevel = .accurate
      req.recognitionLanguages = ["zh-Hans", "en-US"]
      req.usesLanguageCorrection = true
      try? VNImageRequestHandler(cgImage: crop, options: [:]).perform([req])
      for o in req.results ?? [] {
        guard let c = o.topCandidates(1).first else { continue }
        let b = o.boundingBox
        let y = top + (1 - b.maxY) * h
        // 겹침 구간의 중복은 아래쪽 조각에서만 받는다
        if top > 0 && y < top + overlap / 2 { continue }
        if top + h < H && y > top + step + overlap / 2 { continue }
        lines.append(["t": c.string, "c": c.confidence, "x": b.minX * W, "y": y, "w": b.width * W, "h": b.height * h])
      }
      top += step
    }
    let obj: [String: Any] = ["f": path, "w": cg.width, "h": cg.height, "lines": lines]
    if let d = try? JSONSerialization.data(withJSONObject: obj), let s = String(data: d, encoding: .utf8) { print(s) }
  }
}
