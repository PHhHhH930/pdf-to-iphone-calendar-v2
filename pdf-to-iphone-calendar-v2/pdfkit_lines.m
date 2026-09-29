#import <Foundation/Foundation.h>
#import <PDFKit/PDFKit.h>

static void emit(NSDictionary *record) {
    NSData *data = [NSJSONSerialization dataWithJSONObject:record options:0 error:NULL];
    fwrite(data.bytes, 1, data.length, stdout);
    fputc('\n', stdout);
}

static NSMutableDictionary *record(NSUInteger page, NSRect box, NSString *text, NSString *kind) {
    return [@{@"page": @(page), @"x": @(box.origin.x), @"y": @(box.origin.y),
              @"width": @(box.size.width), @"height": @(box.size.height),
              @"text": text ?: @"", @"type": kind} mutableCopy];
}

int main(int argc, const char *argv[]) {
    @autoreleasepool {
        if (argc < 2) {
            fputs("usage: pdfkit_lines PDF\n", stderr);
            return 2;
        }

        NSString *path = [NSString stringWithUTF8String:argv[1]];
        PDFDocument *document = [[PDFDocument alloc]
            initWithURL:[NSURL fileURLWithPath:path]];
        if (!document || document.isLocked || document.pageCount == 0) {
            fputs("cannot open PDF, or PDF is locked/empty\n", stderr);
            return 3;
        }

        NSRegularExpression *days = [NSRegularExpression
            regularExpressionWithPattern:@"(?:星期|周)[一二三四五六日天]" options:0 error:NULL];
        for (NSUInteger pageIndex = 0; pageIndex < document.pageCount; pageIndex++) {
            PDFPage *page = [document pageAtIndex:pageIndex];
            NSString *pageText = page.string ?: @"";
            NSMutableDictionary *info = record(pageIndex + 1, [page boundsForBox:kPDFDisplayBoxMediaBox], @"", @"page");
            info[@"rotation"] = @(page.rotation);
            emit(info);
            for (NSTextCheckingResult *match in [days matchesInString:pageText options:0 range:NSMakeRange(0, pageText.length)]) {
                PDFSelection *s = [page selectionForRange:match.range];
                emit(record(pageIndex + 1, [s boundsForPage:page], s.string, @"weekday"));
            }
            PDFSelection *whole = [page selectionForRange:
                NSMakeRange(0, page.numberOfCharacters)];
            for (PDFSelection *line in [whole selectionsByLine]) {
                PDFRect bounds = [line boundsForPage:page];
                NSString *text = [line.string
                    stringByReplacingOccurrencesOfString:@"\n" withString:@""];
                emit(record(pageIndex + 1, bounds, text, @"line"));
            }
            // Character bounds prevent adjacent weekday cells being merged into one line.
            [pageText enumerateSubstringsInRange:NSMakeRange(0, pageText.length)
                options:NSStringEnumerationByComposedCharacterSequences
                usingBlock:^(NSString *s, NSRange range, NSRange enclosing, BOOL *stop) {
                    if ([s rangeOfCharacterFromSet:[NSCharacterSet whitespaceAndNewlineCharacterSet].invertedSet].location == NSNotFound) return;
                    PDFSelection *selection = [page selectionForRange:range];
                    NSRect box = [selection boundsForPage:page];
                    if (!NSIsEmptyRect(box)) emit(record(pageIndex + 1, box, s, @"char"));
                }];
        }
    }
    return 0;
}
