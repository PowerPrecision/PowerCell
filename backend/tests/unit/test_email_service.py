"""
Testes unitários para serviços de email.
"""
import pytest
from datetime import datetime, timezone
import re


class TestEmailParsing:
    """Testes para parsing de emails."""
    
    def test_email_address_extraction(self):
        """Testa extracção de endereços de email."""
        def extract_email(text):
            pattern = r'[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+'
            matches = re.findall(pattern, text)
            return matches[0] if matches else None
        
        test_cases = [
            ("From: user@example.com", "user@example.com"),
            ("<contact@empresa.pt>", "contact@empresa.pt"),
            ("Email: test.user+tag@domain.co.uk", "test.user+tag@domain.co.uk"),
        ]
        
        for text, expected in test_cases:
            result = extract_email(text)
            assert result == expected
    
    def test_email_name_extraction(self):
        """Testa extracção de nome do remetente."""
        def extract_name_and_email(from_header):
            # Formato: "Nome <email>" ou apenas "email"
            match = re.match(r'^"?([^"<]+)"?\s*<([^>]+)>$', from_header)
            if match:
                return match.group(1).strip(), match.group(2).strip()
            
            # Apenas email
            email_match = re.match(r'^([a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+)$', from_header)
            if email_match:
                return None, email_match.group(1)
            
            return None, None
        
        test_cases = [
            ("João Silva <joao@test.com>", ("João Silva", "joao@test.com")),
            ('"Maria Santos" <maria@empresa.pt>', ("Maria Santos", "maria@empresa.pt")),
            ("admin@test.com", (None, "admin@test.com")),
        ]
        
        for header, expected in test_cases:
            result = extract_name_and_email(header)
            assert result == expected
    
    def test_cc_parsing(self):
        """Testa parsing de campo CC."""
        def parse_cc_field(cc_string):
            if not cc_string:
                return []
            
            # Separar por vírgula
            parts = cc_string.split(",")
            emails = []
            
            for part in parts:
                part = part.strip()
                # Extrair email de formato "Nome <email>"
                match = re.search(r'<([^>]+)>', part)
                if match:
                    emails.append(match.group(1))
                elif "@" in part:
                    emails.append(part)
            
            return emails
        
        test_cases = [
            ("user1@test.com, user2@test.com", ["user1@test.com", "user2@test.com"]),
            ("João <joao@test.com>, Maria <maria@test.com>", ["joao@test.com", "maria@test.com"]),
            ("", []),
            (None, []),
        ]
        
        for cc_str, expected in test_cases:
            result = parse_cc_field(cc_str)
            assert result == expected


class TestEmailSubjectParsing:
    """Testes para parsing de assuntos de email."""
    
    def test_subject_decoding(self):
        """Testa decodificação de assuntos encoded."""
        def decode_subject(subject):
            if not subject:
                return ""
            
            # Simples: remover prefixos de encoding
            # Em produção, usaria email.header.decode_header
            if subject.startswith("=?"):
                # Simplificação para teste
                return subject
            
            return subject.strip()
        
        test_cases = [
            ("Assunto Normal", "Assunto Normal"),
            ("  Assunto com espaços  ", "Assunto com espaços"),
        ]
        
        for subject, expected in test_cases:
            result = decode_subject(subject)
            assert result == expected
    
    def test_reply_subject_detection(self):
        """Testa detecção de emails de resposta."""
        def is_reply(subject):
            if not subject:
                return False
            prefixes = ["re:", "res:", "fw:", "fwd:", "enc:"]
            return any(subject.lower().strip().startswith(p) for p in prefixes)
        
        reply_subjects = ["Re: Assunto", "RE: Test", "Fw: Documento"]
        original_subjects = ["Novo Pedido", "Documento para análise"]
        
        for subject in reply_subjects:
            assert is_reply(subject)
        
        for subject in original_subjects:
            assert not is_reply(subject)
    
    def test_thread_id_extraction(self):
        """Testa extracção de ID de thread."""
        def get_thread_id(message_id, in_reply_to):
            # Se é resposta, usa o ID do email original
            if in_reply_to:
                return in_reply_to.strip("<>")
            # Caso contrário, usa o próprio ID
            return message_id.strip("<>") if message_id else None
        
        test_cases = [
            ("<msg123@test.com>", None, "msg123@test.com"),
            ("<msg456@test.com>", "<msg123@test.com>", "msg123@test.com"),
        ]
        
        for msg_id, reply_to, expected in test_cases:
            result = get_thread_id(msg_id, reply_to)
            assert result == expected


class TestEmailAttachments:
    """Testes para processamento de anexos."""
    
    def test_attachment_detection(self):
        """Testa detecção de anexos."""
        def has_attachments(email_parts):
            for part in email_parts:
                content_disposition = part.get("content_disposition", "")
                if "attachment" in content_disposition.lower():
                    return True
            return False
        
        with_attachment = [{"content_disposition": "attachment; filename=doc.pdf"}]
        without_attachment = [{"content_disposition": "inline"}]
        
        assert has_attachments(with_attachment)
        assert not has_attachments(without_attachment)
    
    def test_filename_extraction(self):
        """Testa extracção de nome de ficheiro."""
        def extract_filename(content_disposition):
            # Primeiro tentar filename normal
            match = re.search(r'filename="([^"]+)"', content_disposition)
            if match:
                return match.group(1)
            
            # Tentar sem aspas
            match = re.search(r'filename=([^;\s]+)', content_disposition)
            if match:
                return match.group(1)
            
            return None
        
        test_cases = [
            ('attachment; filename="documento.pdf"', "documento.pdf"),
            ("attachment; filename=report.xlsx", "report.xlsx"),
        ]
        
        for disposition, expected in test_cases:
            result = extract_filename(disposition)
            assert result == expected, f"Expected '{expected}', got '{result}'"
    
    def test_mime_type_validation(self):
        """Testa validação de tipos MIME."""
        ALLOWED_TYPES = [
            "application/pdf",
            "image/jpeg",
            "image/png",
            "application/msword",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        ]
        
        BLOCKED_TYPES = [
            "application/x-executable",
            "application/x-msdownload",
            "text/html",  # Pode conter scripts
        ]
        
        def is_allowed_attachment(mime_type):
            return mime_type in ALLOWED_TYPES
        
        for mime in ALLOWED_TYPES:
            assert is_allowed_attachment(mime)
        
        for mime in BLOCKED_TYPES:
            assert not is_allowed_attachment(mime)


class TestEmailBodyProcessing:
    """Testes para processamento de corpo de email."""
    
    def test_html_to_text(self):
        """Testa conversão de HTML para texto."""
        def html_to_text(html):
            if not html:
                return ""
            
            # Remover tags HTML (simplificado)
            text = re.sub(r'<br\s*/?>', '\n', html)
            text = re.sub(r'<[^>]+>', '', text)
            text = re.sub(r'&nbsp;', ' ', text)
            text = re.sub(r'&lt;', '<', text)
            text = re.sub(r'&gt;', '>', text)
            text = re.sub(r'&amp;', '&', text)
            
            return text.strip()
        
        test_cases = [
            ("<p>Olá</p>", "Olá"),
            ("Texto <b>bold</b>", "Texto bold"),
            ("Linha1<br>Linha2", "Linha1\nLinha2"),
            ("&nbsp;Espaço&nbsp;", "Espaço"),
        ]
        
        for html, expected in test_cases:
            result = html_to_text(html)
            assert result == expected
    
    def test_signature_detection(self):
        """Testa detecção de assinatura."""
        def remove_signature(body):
            # Detectar linhas de assinatura comuns
            signature_markers = [
                "\n-- \n",
                "\n--\n",
                "\nAtenciosamente,",
                "\nCumprimentos,",
                "\nBest regards,",
            ]
            
            for marker in signature_markers:
                if marker in body:
                    body = body.split(marker)[0]
            
            return body.strip()
        
        email_body = "Olá,\n\nMensagem.\n\n-- \nJoão Silva\nConsultor"
        result = remove_signature(email_body)
        
        assert "Mensagem" in result
        assert "Consultor" not in result
    
    def test_embedded_images_detection(self):
        """Testa detecção de imagens embutidas (cid:)."""
        def has_embedded_images(html):
            return "cid:" in html
        
        html_with_cid = '<img src="cid:image001.png@01D12345.6789ABCD">'
        html_without_cid = '<img src="https://example.com/image.png">'
        
        assert has_embedded_images(html_with_cid)
        assert not has_embedded_images(html_without_cid)


class TestEmailSending:
    """Testes para envio de emails."""
    
    def test_recipient_validation(self):
        """Testa validação de destinatários."""
        def validate_recipients(to, cc=None, bcc=None):
            all_recipients = list(to)
            if cc:
                all_recipients.extend(cc)
            if bcc:
                all_recipients.extend(bcc)
            
            email_pattern = r'^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$'
            
            for email in all_recipients:
                if not re.match(email_pattern, email):
                    return False
            
            return len(all_recipients) > 0
        
        # Válido
        assert validate_recipients(["user@test.com"])
        assert validate_recipients(["user1@test.com"], cc=["user2@test.com"])
        
        # Inválido
        assert not validate_recipients(["invalid"])
        assert not validate_recipients([])
    
    def test_email_size_limit(self):
        """Testa limite de tamanho de email."""
        MAX_SIZE_MB = 25
        MAX_SIZE_BYTES = MAX_SIZE_MB * 1024 * 1024
        
        def is_within_limit(body_size, attachments_size):
            return (body_size + attachments_size) <= MAX_SIZE_BYTES
        
        # 10MB body + 10MB attachments = OK
        assert is_within_limit(10 * 1024 * 1024, 10 * 1024 * 1024)
        
        # 20MB body + 10MB attachments = TOO BIG
        assert not is_within_limit(20 * 1024 * 1024, 10 * 1024 * 1024)
    
    def test_smtp_connection_config(self):
        """Testa configuração de conexão SMTP."""
        config = {
            "host": "smtp.example.com",
            "port": 587,
            "use_tls": True,
            "username": "user@example.com",
            "password": "secret"
        }
        
        # Verificar campos obrigatórios
        required = ["host", "port", "username", "password"]
        for field in required:
            assert field in config
        
        # Portas válidas
        valid_ports = [25, 465, 587, 2525]
        assert config["port"] in valid_ports


class TestEmailFiltering:
    """Testes para filtragem de emails."""
    
    def test_spam_detection(self):
        """Testa detecção de spam."""
        def is_spam(subject, sender, body):
            spam_keywords = ["viagra", "lottery", "winner", "click here", "free money"]
            
            content = f"{subject} {body}".lower()
            
            for keyword in spam_keywords:
                if keyword in content:
                    return True
            
            return False
        
        spam_email = {
            "subject": "You are a winner!",
            "sender": "spam@fake.com",
            "body": "Click here to claim your lottery prize"
        }
        
        normal_email = {
            "subject": "Processo de crédito",
            "sender": "cliente@empresa.pt",
            "body": "Bom dia, gostaria de informação."
        }
        
        assert is_spam(**spam_email)
        assert not is_spam(**normal_email)
    
    def test_client_email_matching(self):
        """Testa matching de emails com clientes."""
        def find_matching_client(email, clients):
            email_lower = email.lower()
            
            for client in clients:
                if client.get("email", "").lower() == email_lower:
                    return client
                
                # Também verificar emails alternativos
                alt_emails = client.get("alternative_emails", [])
                if email_lower in [e.lower() for e in alt_emails]:
                    return client
            
            return None
        
        clients = [
            {"id": "1", "email": "joao@test.com", "alternative_emails": ["joaosilva@gmail.com"]},
            {"id": "2", "email": "maria@test.com"},
        ]
        
        assert find_matching_client("joao@test.com", clients)["id"] == "1"
        assert find_matching_client("joaosilva@gmail.com", clients)["id"] == "1"
        assert find_matching_client("unknown@test.com", clients) is None
    
    def test_date_range_filter(self):
        """Testa filtro por intervalo de datas."""
        def is_within_date_range(email_date, start_date, end_date):
            if isinstance(email_date, str):
                email_date = datetime.fromisoformat(email_date.replace("Z", "+00:00"))
            
            return start_date <= email_date <= end_date
        
        now = datetime.now(timezone.utc)
        yesterday = now - timedelta(days=1)
        last_week = now - timedelta(days=7)
        
        email_date = now - timedelta(days=3)
        
        # Dentro do intervalo
        assert is_within_date_range(email_date.isoformat(), last_week, now)
        
        # Fora do intervalo
        assert not is_within_date_range(email_date.isoformat(), yesterday, now)


# Import necessário para testes com timedelta
from datetime import timedelta
