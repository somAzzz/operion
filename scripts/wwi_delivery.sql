CREATE OR ALTER PROCEDURE dbo.operion_read_delivery
    @order_id int, @customer_ids nvarchar(max), @supplier_ids nvarchar(max)
AS
BEGIN
    SET NOCOUNT ON;
    SELECT COALESCE((
    SELECT o.OrderID AS order_id, o.CustomerID AS customer_id, o.ContactPersonID AS contact_person_id,
           o.ExpectedDeliveryDate AS expected_date, o.OrderDate AS order_date,
           CONCAT(CONVERT(varchar(27), SYSUTCDATETIME(), 126), 'Z') AS queried_at,
           JSON_QUERY(COALESCE((SELECT i.InvoiceID AS invoice_id, i.OrderID AS invoice_order_id,
                   i.CustomerID AS invoice_customer_id, i.IsCreditNote AS credit_note,
                   i.ConfirmedDeliveryTime AS confirmed_at,
                   CAST(CASE WHEN NULLIF(i.ConfirmedReceivedBy, '') IS NULL
                             THEN 0 ELSE 1 END AS bit) AS has_recipient
            FROM Sales.Invoices AS i WHERE i.OrderID = o.OrderID
            ORDER BY i.InvoiceID FOR JSON PATH, INCLUDE_NULL_VALUES), N'[]')) AS invoices,
           JSON_QUERY(COALESCE((SELECT CONCAT('wwi:sales_order_line:', l.OrderLineID) AS canonical_id,
                   l.StockItemID AS stock_item_id, l.Quantity AS ordered_quantity, l.PickedQuantity AS picked_quantity,
                   p.PackageTypeName AS uom
            FROM Sales.OrderLines AS l
            JOIN Warehouse.PackageTypes AS p ON p.PackageTypeID = l.PackageTypeID
            WHERE l.OrderID = o.OrderID
            ORDER BY l.OrderLineID FOR JSON PATH, INCLUDE_NULL_VALUES), N'[]')) AS lines,
           JSON_QUERY(COALESCE((
               SELECT t.StockItemTransactionID AS issue_id, t.InvoiceID AS invoice_id,
                      t.StockItemID AS stock_item_id, t.Quantity AS quantity,
                      t.TransactionOccurredWhen AS issued_at,
                      JSON_QUERY(COALESCE((
                          SELECT TOP (2) r.StockItemTransactionID AS receipt_id,
                                 r.StockItemID AS stock_item_id, r.Quantity AS quantity,
                                 r.TransactionOccurredWhen AS received_at, po.PurchaseOrderID AS purchase_order_id,
                                 po.SupplierID AS supplier_id, s.SupplierName AS supplier
                          FROM Warehouse.StockItemTransactions AS r
                          JOIN Application.TransactionTypes AS rt ON rt.TransactionTypeID = r.TransactionTypeID
                          JOIN Purchasing.PurchaseOrders AS po ON po.PurchaseOrderID = r.PurchaseOrderID
                                                              AND po.SupplierID = r.SupplierID
                          JOIN Purchasing.Suppliers AS s ON s.SupplierID = po.SupplierID
                          WHERE r.StockItemID = t.StockItemID AND r.TransactionOccurredWhen <= t.TransactionOccurredWhen
                            AND rt.TransactionTypeName = 'Stock Receipt' AND r.Quantity > 0
                            AND po.SupplierID IN (SELECT value FROM OPENJSON(@supplier_ids))
                          ORDER BY r.TransactionOccurredWhen DESC, r.StockItemTransactionID DESC
                          FOR JSON PATH), N'[]')) AS prior_receipts
               FROM Warehouse.StockItemTransactions AS t
               JOIN Sales.Invoices AS i ON i.InvoiceID = t.InvoiceID AND i.CustomerID = t.CustomerID
               JOIN Application.TransactionTypes AS it ON it.TransactionTypeID = t.TransactionTypeID
               WHERE i.OrderID = o.OrderID AND t.CustomerID = o.CustomerID AND i.IsCreditNote = 0
                 AND it.TransactionTypeName = 'Stock Issue' AND t.Quantity < 0
               ORDER BY t.TransactionOccurredWhen, t.StockItemTransactionID
               FOR JSON PATH), N'[]')) AS issues
    FROM Sales.Orders AS o
    WHERE o.OrderID = @order_id AND o.CustomerID IN (SELECT value FROM OPENJSON(@customer_ids))
    FOR JSON PATH, INCLUDE_NULL_VALUES
    ), N'[]') AS payload;
END;
GO
