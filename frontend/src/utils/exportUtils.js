import { saveAs } from 'file-saver';
import jsPDF from 'jspdf';
import 'jspdf-autotable';
/**
 * Export chat messages as Markdown file
 */
export const exportChatAsMarkdown = (messages, sessionTitle = 'Chat Export') => {
  // Generate markdown content
  let markdown = `# ${sessionTitle}\n\n`;
  markdown += `*Exported on ${new Date().toLocaleString()}*\n\n`;
  markdown += `---\n\n`;

  messages.forEach((message, index) => {
    const role = message.role === 'user' ? '**You**' : '**Assistant**';
    const timestamp = new Date(message.created_at).toLocaleString();
    
    markdown += `### ${role} - *${timestamp}*\n\n`;
    markdown += `${message.content}\n\n`;

    // Add sources if available
    if (message.sources && message.sources.length > 0) {
      markdown += `**Sources:**\n`;
      message.sources.forEach((source, idx) => {
        markdown += `${idx + 1}. ${source}\n`;
      });
      markdown += `\n`;
    }

    markdown += `---\n\n`;
  });

  // Create blob and download
  const blob = new Blob([markdown], { type: 'text/markdown;charset=utf-8' });
  const filename = `${sanitizeFilename(sessionTitle)}_${Date.now()}.md`;
  saveAs(blob, filename);
};

/**
 * Sanitize filename - remove invalid characters
 */
const sanitizeFilename = (name) => {
  return name
    .replace(/[^a-z0-9]/gi, '_')
    .replace(/_+/g, '_')
    .toLowerCase()
    .substring(0, 50);
};
/**
 * Export chat messages as PDF file
 */
export const exportChatAsPDF = (messages, sessionTitle = 'Chat Export') => {
  const doc = new jsPDF();
  
  // PDF styling
  const pageWidth = doc.internal.pageSize.getWidth();
  const margin = 15;
  const maxWidth = pageWidth - (margin * 2);
  let yPosition = 20;

  // Title
  doc.setFontSize(20);
  doc.setFont(undefined, 'bold');
  doc.text(sessionTitle, margin, yPosition);
  
  yPosition += 10;
  
  // Export date
  doc.setFontSize(10);
  doc.setFont(undefined, 'italic');
  doc.setTextColor(100);
  doc.text(`Exported on ${new Date().toLocaleString()}`, margin, yPosition);
  
  yPosition += 10;
  
  // Separator line
  doc.setDrawColor(200);
  doc.line(margin, yPosition, pageWidth - margin, yPosition);
  yPosition += 10;

  // Process each message
  messages.forEach((message, index) => {
    // Check if we need a new page
    if (yPosition > 260) {
      doc.addPage();
      yPosition = 20;
    }

    // Role header
    doc.setFontSize(12);
    doc.setFont(undefined, 'bold');
    const role = message.role === 'user' ? 'You' : 'Assistant';
    const roleColor = message.role === 'user' ? [59, 130, 246] : [124, 58, 237]; // Blue or Purple
    doc.setTextColor(...roleColor);
    doc.text(role, margin, yPosition);
    
    // Timestamp
    doc.setFontSize(9);
    doc.setFont(undefined, 'normal');
    doc.setTextColor(150);
    const timestamp = new Date(message.created_at).toLocaleString();
    doc.text(timestamp, margin + 25, yPosition);
    
    yPosition += 7;

    // Message content
    doc.setFontSize(10);
    doc.setFont(undefined, 'normal');
    doc.setTextColor(0);
    
    const lines = doc.splitTextToSize(message.content, maxWidth);
    lines.forEach(line => {
      if (yPosition > 270) {
        doc.addPage();
        yPosition = 20;
      }
      doc.text(line, margin, yPosition);
      yPosition += 5;
    });

    yPosition += 3;

    // Sources
    if (message.sources && message.sources.length > 0) {
      doc.setFontSize(9);
      doc.setFont(undefined, 'bold');
      doc.setTextColor(100);
      doc.text('Sources:', margin, yPosition);
      yPosition += 5;

      doc.setFont(undefined, 'normal');
      message.sources.forEach((source, idx) => {
        if (yPosition > 275) {
          doc.addPage();
          yPosition = 20;
        }
        const sourceText = `${idx + 1}. ${source}`;
        const sourceLines = doc.splitTextToSize(sourceText, maxWidth - 5);
        sourceLines.forEach(sourceLine => {
          doc.text(sourceLine, margin + 5, yPosition);
          yPosition += 4;
        });
      });
      yPosition += 3;
    }

    // Separator
    yPosition += 5;
    doc.setDrawColor(230);
    doc.line(margin, yPosition, pageWidth - margin, yPosition);
    yPosition += 10;
  });

  // Save PDF
  const filename = `${sanitizeFilename(sessionTitle)}_${Date.now()}.pdf`;
  doc.save(filename);
};

/**
 * Export all sessions list as Markdown
 */
export const exportSessionsListAsMarkdown = (sessions) => {
  let markdown = `# Chat Sessions List\n\n`;
  markdown += `*Exported on ${new Date().toLocaleString()}*\n\n`;
  markdown += `Total Sessions: ${sessions.length}\n\n`;
  markdown += `---\n\n`;

  sessions.forEach((session, index) => {
    markdown += `## ${index + 1}. ${session.title || `Session ${session.id}`}\n\n`;
    markdown += `- **Topic:** ${session.topic || 'General'}\n`;
    markdown += `- **Created:** ${new Date(session.created_at).toLocaleString()}\n`;
    if (session.last_message_time) {
      markdown += `- **Last Activity:** ${new Date(session.last_message_time).toLocaleString()}\n`;
    }
    markdown += `\n---\n\n`;
  });

  const blob = new Blob([markdown], { type: 'text/markdown;charset=utf-8' });
  saveAs(blob, `chat_sessions_${Date.now()}.md`);
};
