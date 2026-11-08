# failed_dead_breakdown
Data source: `data\kb_admin\state.db` table `files`, filtered by current `status in ('failed', 'dead')`.

## Summary
| status | category | reason‑key | count |
|---|---|---|---|
| dead | bad‑zip‑or‑fake‑office | File is not a zip file | 17 |
| dead | broken‑pool | worker pool broken while submitting tasks | 5 |
| dead | embedding‑input‑too‑long | maximum input length is 8192 tokens | 1 |
| dead | emf‑metafile‑ocr‑failure | cannot render metafile / no embedded image | 1 |
| dead | other | C:\Users\234393\Desktop\jap‑cycle‑poc\.venv312\Lib\site‑packages\openpyxl\worksheet\header_footer.py:48: UserWarning: Ca | 2 |
| dead | other | process_one failed for C:\Users\234393\Desktop\jap‑cycle‑poc\sample_docs\21_新契約\【Medical2023 Rev2】ビジネス要件定義書_新契約_v1.1_202 | 1 |
| dead | process‑abruptly‑terminated | A process in the process pool was terminated abruptly | 3 |
| dead | processing‑timeout | processing timed out after ... | 5 |
| dead | unsupported‑file‑type | unsupported file type | 20 |
| failed | unsupported‑file‑type | unsupported file type | 1 |

## Details

### dead / bad‑zip‑or‑fake‑office / File is not a zip file (17)
| file_id | path | error_reason |
|---|---|---|
| 17 | C:\Users\234393\Desktop\jap‑cycle‑poc\sample_docs\SRS\ETL_KLIP連動\~$業務設計要約【ETL(KLIP連動)】(23‑000305)_Medical Revision2023_Rev2 Ver0.1.xlsx | The file is not a valid zip‑based Office document. |
| 19 | C:\Users\234393\Desktop\jap‑cycle‑poc\sample_docs\SRS\FWDnavi\90_QA\【WL】FWDnaviの確認事項 _230215_OP回答追記.xlsx | The file is not a valid zip‑based Office document. |
| 29 | C:\Users\234393\Desktop\jap‑cycle‑poc\sample_docs\24_顧客サービス部(保全)\~$【Medical Revision2 & 1.5 2023】ビジネス要件定義書_顧サ(保全)ver1.1.xlsx | The file is not a valid zip‑based Office document. |
| 33 | C:\Users\234393\Desktop\jap‑cycle‑poc\sample_docs\21_新契約\02_画面要件\IWF\~$【WL2023・Medical2023Rev2】画面要件定義書(IWF)_v1.0_20230330.xlsx | The file is not a valid zip‑based Office document. |
| 48 | C:\Users\234393\Desktop\jap‑cycle‑poc\sample_docs\SRS\SalesTool\01_設計書\~$業務設計要約(MR2023Rev2)_SalesTool_設計書_1.2.xlsx | The file is not a valid zip‑based Office document. |
| 77 | C:\Users\234393\Desktop\jap‑cycle‑poc\sample_docs\商品仕様書\【Medical Revision 2023】FU商品仕様書 _20230329_v1.3.xlsx | The file is not a valid zip‑based Office document. |
| 78 | C:\Users\234393\Desktop\jap‑cycle‑poc\sample_docs\商品仕様書\【Medical Revision 2023】SI商品仕様書 _20230329_v1.3.xlsx | The file is not a valid zip‑based Office document. |
| 95 | C:\Users\234393\Desktop\jap‑cycle‑poc\sample_docs\71_帳票要件\帳票要件シート_業務メール\~$【03_帳票要件シート】SGML0028_保険金等支払通知_SPSA00_v2.1.xlsx | The file is not a valid zip‑based Office document. |
| 96 | C:\Users\234393\Desktop\jap‑cycle‑poc\sample_docs\71_帳票要件\帳票要件シート_業務メール\【03_帳票要件シート】SPSA0K_生保金支払通知_SPSA0K_v2.1.xlsx | The file is not a valid zip‑based Office document. |
| 97 | C:\Users\234393\Desktop\jap‑cycle‑poc\sample_docs\71_帳票要件\帳票要件シート_業務メール\【03_帳票要件シート】SPSA0K_生保金支払通知_SPSA0K_v2.1.xlsx | The file is not a valid zip‑based Office document. |
| 101 | C:\Users\234393\Desktop\jap‑cycle‑poc\sample_docs\41_数理\old\~$【Medical Revision2 2023_Rev2】ユーザー要件定義書_v1.0_数理_3.xlsx | The file is not a valid zip‑based Office document. |
| 104 | C:\Users\234393\Desktop\jap‑cycle‑poc\sample_docs\41_数理\old\【Medical Revision2 2023_Rev2】ユーザー要件定義書_v1.1_数理_3.xlsx | The file is not a valid zip‑based Office document. |
| 111 | C:\Users\234393\Desktop\jap‑cycle‑poc\sample_docs\41_数理\old\【Medical Revision2 2023_Rev2】ユーザー要件定義書_v1.2_数理_3.xlsx | The file is not a valid zip‑based Office document. |
| 120 | C:\Users\234393\Desktop\jap‑cycle‑poc\sample_docs\41_数理\old\【Medical Revision2 2023_Rev2】ユーザー要件定義書_v1.3_数理_3.xlsx | The file is not a valid zip‑based Office document. |
| 124 | C:\Users\234393\Desktop\jap‑cycle‑poc\sample_docs\41_数理\old\【Medical Revision2 2023_Rev2】ユーザー要件定義書_v1.4_数理_3.xlsx | The file is not a valid zip‑based Office document. |
| 127 | C:\Users\234393\Desktop\jap‑cycle‑poc\sample_docs\41_数理\old\【Medical Revision2 2023_Rev2】ユーザー要件定義書_v1.5_数理_3.xlsx | The file is not a valid zip‑based Office document. |
| 142 | C:\Users\234393\Desktop\jap‑cycle‑poc\sample_docs\24_顧客サービス部(保全)\old\~$【Medical Revision2 2023】ビジネス要件定義書_顧サ(保全)ver1.0.xlsx | The file is not a valid zip‑based Office document. |

### dead / broken‑pool / worker pool broken while submitting tasks (5)
| file_id | path | error_reason |
|---|---|---|
| 126 | C:\Users\234393\Desktop\jap‑cycle‑poc\sample_docs\22_事務管理帳票\Thumbs.db | Worker process pool broke while submitting this file. |
| 159 | C:\Users\234393\Desktop\jap‑cycle‑poc\sample_docs\21_新契約\01_機能要件\01_ルール記述書 - ショートカット (PLフォルダ変わることに注意).lnk | Worker process pool broke while submitting this file. |
| 170 | C:\Users\234393\Desktop\jap‑cycle‑poc\sample_docs\21_新契約\02_画面要件\MPPL\Thumbs.db | Worker process pool broke while submitting this file. |
| 186 | C:\Users\234393\Desktop\jap‑cycle‑poc\sample_docs\21_新契約\02_画面要件\SalesTool\Thumbs.db | Worker process pool broke while submitting this file. |
| 203 | C:\Users\234393\Desktop\jap‑cycle‑poc\sample_docs\21_新契約\Thumbs.db | Worker process pool broke while submitting this file. |

### dead / embedding‑input‑too‑long / maximum input length is 8192 tokens (1)
| file_id | path | error_reason |
|---|---|---|
| 63 | C:\Users\234393\Desktop\jap‑cycle‑poc\sample_docs\SRS\UWS_Rule\~$【RuleEngine_PPL】搭載ルール一覧.xlsm | Embedding input exceeded the 8192‑token limit. |

### dead / emf‑metafile‑ocr‑failure / cannot render metafile / no embedded image (1)
| file_id | path | error_reason |
|---|---|---|
| 6 | C:\Users\234393\Desktop\jap‑cycle‑poc\sample_docs\Training\Training\#09_契約管理システム.pptx | OCR could not render EMF/metafile content into a usable image. |

### dead / other / C:\Users\234393\Desktop\jap‑cycle‑poc\.venv312\Lib\site‑packages\openpyxl\worksheet\header_footer.py:48: UserWarning: Ca (2)
| file_id | path | error_reason |
|---|---|---|
| 144 | C:\Users\234393\Desktop\jap‑cycle‑poc\sample_docs\24_顧客サービス部(保全)\old\【Medical Revision2 2023】画面要件定義書(LifeJ)保全_v1.0(ドラフト).xlsx | C:\Users\234393\Desktop\jap‑cycle‑poc\.venv312\Lib\site‑packages\openpyxl\worksheet\header_footer.py:48: UserWarning: Cannot parse header or footer so it will be b |
| 161 | C:\Users\234393\Desktop\jap‑cycle‑poc\sample_docs\21_新契約\01_機能要件\【WL2023‑Medical2023Rev2】SalesTool_関連資料_取込条件_v1.0.xlsx | C:\Users\234393\Desktop\jap‑cycle‑poc\.venv312\Lib\site‑packages\openpyxl\worksheet\header_footer.py:48: UserWarning: Cannot parse header or footer so it will be b |

### dead / other / process_one failed for C:\Users\234393\Desktop\jap‑cycle‑poc\sample_docs\21_新契約\【Medical2023 Rev2】ビジネス要件定義書_新契約_v1.1_202 (1)
| file_id | path | error_reason |
|---|---|---|
| 205 | C:\Users\234393\Desktop\jap‑cycle‑poc\sample_docs\21_新契約\【Medical2023 Rev2】ビジネス要件定義書_新契約_v1.1_20230405.xlsx | process_one failed for C:\Users\234393\Desktop\jap‑cycle‑poc\sample_docs\21_新契約\【Medical2023 Rev2】ビジネス要件定義書_新契約_v1.1_20230405.xlsx: Connection error. |

### dead / process‑abruptly‑terminated / A process in the process pool was terminated abruptly (3)
| file_id | path | error_reason |
|---|---|---|
| 100 | C:\Users\234393\Desktop\jap‑cycle‑poc\sample_docs\41_数理\old\【Medical Revision 2023_Rev2】ユーザー要件定義書_v1.0_数理_3.xlsb | A worker subprocess terminated abruptly during processing. |
| 167 | C:\Users\234393\Desktop\jap‑cycle‑poc\sample_docs\21_新契約\02_画面要件\IWF\Thumbs.db | A worker subprocess terminated abruptly during processing. |
| 177 | C:\Users\234393\Desktop\jap‑cycle‑poc\sample_docs\21_新契約\02_画面要件\PPL\Thumbs.db | A worker subprocess terminated abruptly during processing. |

### dead / processing‑timeout / processing timed out after ... (5)
| file_id | path | error_reason |
|---|---|---|
| 22 | C:\Users\234393\Desktop\jap‑cycle‑poc\sample_docs\SRS\FWDnavi\90_QA\FWDnavi_システムテスト仕様書_v1.0.docx | Processing exceeded maximum allowed duration. |
| 51 | C:\Users\234393\Desktop\jap‑cycle‑poc\sample_docs\SRS\SalesTool\02_テスト\SalesTool_システムテスト仕様書_v1.0.docx | Processing exceeded maximum allowed duration. |
| 81 | C:\Users\234393\Desktop\jap‑cycle‑poc\sample_docs\71_帳票要件\帳票要件シート_業務メール\SGML0028_保険金等支払通知_SPSA00_v2.1.docx | Processing exceeded maximum allowed duration. |
| 113 | C:\Users\234393\Desktop\jap‑cycle‑poc\sample_docs\41_数理\old\【Medical Revision2 2023_Rev2】ユーザー要件定義書_v1.1_数理_3.docx | Processing exceeded maximum allowed duration. |
| 154 | C:\Users\234393\Desktop\jap‑cycle‑poc\sample_docs\21_新契約\01_機能要件\【Medical2023 Rev2】SalesTool_機能要件定義書_v1.2.docx | Processing exceeded maximum allowed duration. |

### dead / unsupported‑file‑type / unsupported file type (20)
| file_id | path | error_reason |
|---|---|---|
| 18 | C:\Users\234393\Desktop\jap‑cycle‑poc\sample_docs\SRS\ETL_KLIP連動\業務設計要約【ETL(KLIP連動)】(23‑000305)_Medical Revision2023_Rev2 Ver0.1.xlsx | The file type unknown is not supported by the ingestion pipeline. |
| 32 | C:\Users\234393\Desktop\jap‑cycle‑poc\sample_docs\SRS\IWF\Thumbs.db | The file type .db is not supported by the ingestion pipeline. |
| 57 | C:\Users\234393\Desktop\jap‑cycle‑poc\sample_docs\SRS\SalesTool\03_PPL\Thumbs.db | The file type .db is not supported by the ingestion pipeline. |
| 60 | C:\Users\234393\Desktop\jap‑cycle‑poc\sample_docs\SRS\Xuras\RE_【Biz承認依頼】MEDICAL_REVISION2システム仕様定義.msg | The file type .msg is not supported by the ingestion pipeline. |
| 68 | C:\Users\234393\Desktop\jap‑cycle‑poc\sample_docs\SRS\VPMS\RE_【Biz承認依頼】MedicalRev2システム仕様定義.msg | The file type .msg is not supported by the ingestion pipeline. |
| 71 | C:\Users\234393\Desktop\jap‑cycle‑poc\sample_docs\SRS\Xuras\Thumbs.db | The file type .db is not supported by the ingestion pipeline. |
| 119 | C:\Users\234393\Desktop\jap‑cycle‑poc\sample_docs\26_CS\Xuras(成立前) - ショートカット.lnk | The file type .lnk is not supported by the ingestion pipeline. |
| 132 | C:\Users\234393\Desktop\jap‑cycle‑poc\sample_docs\22_事務管理帳票\【03_帳票要件シート】保険証券・異動承認証印字仕様書(TBL文言定義書)_20230411.xlsx | The file type unknown is not supported by the ingestion pipeline. |
| 133 | C:\Users\234393\Desktop\jap‑cycle‑poc\sample_docs\22_事務管理帳票\【03_帳票要件シート】保険証券・異動承認証印字仕様書(TBL文言定義書)_20230424.xlsx - ショートカット.lnk | The file type .lnk is not supported by the ingestion pipeline. |
| 134 | C:\Users\234393\Desktop\jap‑cycle‑poc\sample_docs\22_事務管理帳票\【03_帳票要件シート】保険証券・異動承認証印字仕様書(TBL文言定義書)_20230609.xlsx | The file type unknown is not supported by the ingestion pipeline. |
| 141 | C:\Users\234393\Desktop\jap‑cycle‑poc\sample_docs\24_顧客サービス部(保全)\old\【Medical Revision2 2023】ビジネス要件定義書_顧サ(保全)ver1.0ドラフト.xlsx | The file type unknown is not supported by the ingestion pipeline. |
| 143 | C:\Users\234393\Desktop\jap‑cycle‑poc\sample_docs\24_顧客サービス部(保全)\【Medical Revision2 & 1.5 2023】ビジネス要件定義書_顧サ(保全)ver1.1.xlsx | The file type unknown is not supported by the ingestion pipeline. |
| 145 | C:\Users\234393\Desktop\jap‑cycle‑poc\sample_docs\24_顧客サービス部(保全)\画面要件\Xuras(成立後)\Thumbs.db | The file type .db is not supported by the ingestion pipeline. |
| 163 | C:\Users\234393\Desktop\jap‑cycle‑poc\sample_docs\21_新契約\02_画面要件\FWD Navi\Thumbs.db | The file type .db is not supported by the ingestion pipeline. |
| 172 | C:\Users\234393\Desktop\jap‑cycle‑poc\sample_docs\21_新契約\02_画面要件\MPPL\【Medical2023 Rev2】画面要件定義書 (MPPL(取扱報告の入力等))_v1.0_20230222.xlsx | The file type unknown is not supported by the ingestion pipeline. |
| 179 | C:\Users\234393\Desktop\jap‑cycle‑poc\sample_docs\21_新契約\03_帳票要件\帳票要件シート\Thumbs.db | The file type .db is not supported by the ingestion pipeline. |
| 182 | C:\Users\234393\Desktop\jap‑cycle‑poc\sample_docs\21_新契約\03_帳票要件\帳票要件シート\【03_帳票要件シート】SGML0028_保険金等支払通知_SPSA00_v2.1.msg | The file type .msg is not supported by the ingestion pipeline. |
| 189 | C:\Users\234393\Desktop\jap‑cycle‑poc\sample_docs\21_新契約\04_帳票出力\Thumbs.db | The file type .db is not supported by the ingestion pipeline. |
| 194 | C:\Users\234393\Desktop\jap‑cycle‑poc\sample_docs\21_新契約\05_テスト\Thumbs.db | The file type .db is not supported by the ingestion pipeline. |
| 199 | C:\Users\234393\Desktop\jap‑cycle‑poc\sample_docs\21_新契約\06_参考資料\Thumbs.db | The file type .db is not supported by the ingestion pipeline. |

### failed / unsupported‑file‑type / unsupported file type (1)
| file_id | path | error_reason |
|---|---|---|
| 103 | C:\Users\234393\Desktop\jap‑cycle‑poc\sample_docs\41_数理\【Medical Revision 2023_Rev2】ユーザー要件定義書_v1.4_数理.xlsb | The file type .xlsb is not supported by the ingestion pipeline. |

---

如果你需要，我还可以帮你做一份**问题根因分析+修复建议**的markdown，直接追加到这个文档后面。